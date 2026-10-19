"""A Discord-native "still working" signal for a conversational turn: the typing indicator.

Discord gives a plain message no progress UI of its own, whether it is a DM, an @mention or
a reply to PetBot (a slash command gets "PetBot is thinking…" from its deferred response).
The typing indicator is the signal Discord intends for a reply that takes a few seconds,
and it is the only one used: no placeholder message is posted, edited or deleted, which
would cost extra API calls per turn, flicker in the channel and land in servers'
message-delete logs.

:func:`think` keeps typing for the whole turn and, at each checkpoint, pauses the way a
person does: it stops re-triggering, lets the current indicator lapse (one trigger lasts
:data:`TYPING_LIFETIME_SECONDS`; Discord has no "stop typing" call), stays quiet for
:data:`PAUSE_SECONDS`, then starts typing again. The checkpoints are the
:data:`THINKING_AFTER_SECONDS` mark and every phase the transport reports
(:class:`~petbot.platform.Phase`: the worker found waking, then up). Sending the answer
clears the indicator, so a turn that finishes mid-pause just answers.

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

#: The checkpoint for an ordinary long turn. Ten seconds is where a wait stops holding
#: attention (Nielsen's response-time limits) and is the life of one typing trigger. It
#: also clears a normal cold start of the core Lambda (~9 s end to end), so routine turns
#: type without a pause.
THINKING_AFTER_SECONDS = 10.0

#: How long one typing trigger shows in Discord's clients.
TYPING_LIFETIME_SECONDS = 10.0

#: How often to re-trigger typing while typing: well inside one trigger's life.
TYPING_REFRESH_SECONDS = 5.0

#: How long the indicator stays off at a checkpoint, once the last trigger has lapsed.
PAUSE_SECONDS = 2.0


async def think[T](
    message: discord.Message,
    work: Coroutine[Any, Any, T],
    *,
    after: float = THINKING_AFTER_SECONDS,
) -> T:
    """Run ``work`` under the typing indicator, pausing it at each checkpoint (see the
    module docstring). Returns ``work``'s result; only ``work`` itself (or a cancellation)
    can raise."""
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
    """Keep ``channel`` showing "PetBot is typing…", pausing once per item on ``pauses``."""
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
