"""A Discord-native "still working" signal for a conversational turn: the typing indicator.

:func:`think` keeps typing for the whole turn and, at each checkpoint, pauses the way a
person does: it stops re-triggering, lets the current indicator lapse (one trigger lasts
:data:`TYPING_LIFETIME_SECONDS`; Discord has no "stop typing" call), stays quiet for
:data:`PAUSE_SECONDS`, then starts typing again. The checkpoints are the
:data:`THINKING_AFTER_SECONDS` mark and every phase the transport reports
(:class:`~petbot.platform.Phase`: the worker found waking, then up).

Typing is cosmetic: a failure to trigger it is logged and never sinks the turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import discord

from petbot.platform import observe

logger = logging.getLogger(__name__)

THINKING_AFTER_SECONDS = 10.0

#: How long one typing trigger shows in Discord's clients.
TYPING_LIFETIME_SECONDS = 10.0

#: How often to re-trigger typing while typing: well inside one trigger's life.
TYPING_REFRESH_SECONDS = 5.0

PAUSE_SECONDS = 2.0


async def think[T](
    message: discord.Message,
    work: Coroutine[Any, Any, T],
    *,
    after: float = THINKING_AFTER_SECONDS,
) -> T:
    phase_changed = asyncio.Event()
    with observe(lambda _phase: phase_changed.set()):
        task = asyncio.ensure_future(work)
    pauses: asyncio.Queue[None] = asyncio.Queue()
    typing = asyncio.create_task(_type(message.channel, pauses))
    loop = asyncio.get_running_loop()
    deadline: float | None = loop.time() + after
    try:
        while not task.done():
            phase_changed.clear()
            changed = asyncio.ensure_future(phase_changed.wait())
            timeout = None if deadline is None else max(0.0, deadline - loop.time())
            await asyncio.wait(
                {task, changed}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            changed.cancel()
            if task.done():
                break
            if phase_changed.is_set():
                pauses.put_nowait(None)
            elif deadline is not None and loop.time() >= deadline:
                deadline = None
                pauses.put_nowait(None)
        return task.result()
    except BaseException:
        task.cancel()
        raise
    finally:
        typing.cancel()


async def _type(channel: discord.abc.Messageable, pauses: asyncio.Queue[None]) -> None:
    loop = asyncio.get_running_loop()
    while True:
        try:
            await channel.typing()
        except Exception:
            logger.warning("couldn't trigger typing", exc_info=True)
        triggered = loop.time()
        try:
            await asyncio.wait_for(pauses.get(), timeout=TYPING_REFRESH_SECONDS)
        except TimeoutError:
            continue
        lapse = max(0.0, triggered + TYPING_LIFETIME_SECONDS - loop.time())
        await asyncio.sleep(lapse + PAUSE_SECONDS)
        # Checkpoints that arrived mid-pause are already served by this one.
        while not pauses.empty():
            pauses.get_nowait()
