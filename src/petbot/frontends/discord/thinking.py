"""A Discord-native "thinking" state for a slow conversational turn.

Discord gives a plain message no built-in progress UI, whether it is a DM, an @mention or a
reply to PetBot (a slash command gets "PetBot is thinking…" from its deferred response).
The typing indicator is the first line of feedback: one trigger lasts ~10 s, so
:func:`think` re-triggers it every :data:`TYPING_REFRESH_SECONDS` for as long as the turn
runs. Beyond that, :func:`think` posts a small placeholder reply in Discord ``-#`` subtext
that says what the turn is actually doing:

* :data:`WAKING` as soon as the transport reports the worker isn't up yet
  (:attr:`~petbot.platform.Phase.WAKING`): that wait is known to be long, so it shows at once;
* :data:`THINKING` once the turn has run for :data:`THINKING_AFTER_SECONDS`, or in place of
  :data:`WAKING` when the worker comes up.

The caller retires the placeholder with :func:`clear` once the real answer is sent, so the
answer lands as a fresh message rather than an "(edited)" one.

Typing and the placeholder are cosmetic: any failure to trigger, post, edit or delete them
is logged and never sinks the turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import discord

from petbot.platform import Phase, observe

logger = logging.getLogger(__name__)

#: When a turn earns a placeholder. Ten seconds is where a wait stops holding attention
#: (Nielsen's response-time limits) and is the life of one typing trigger. It also clears a
#: normal cold start of the core Lambda (~9 s end to end: ~3.4 s init plus the agent run),
#: so routine turns never flash a placeholder.
THINKING_AFTER_SECONDS = 10.0

#: How often to re-trigger typing: well inside one trigger's ~10 s life.
TYPING_REFRESH_SECONDS = 5.0

#: The placeholder while the worker is waking (re-pull ~20 s, then a ~9 s cold start).
WAKING = "-# 💤 waking up… (the first message after a quiet spell takes ~30 s)"

#: The placeholder while the worker runs a long turn.
THINKING = "-# 💭 thinking…"

_TEXT = {Phase.WAKING: WAKING, Phase.THINKING: THINKING}


class _Status:
    """The turn's latest reported phase, plus an event set whenever it changes."""

    def __init__(self) -> None:
        self.phase = Phase.THINKING
        self.changed = asyncio.Event()

    def update(self, phase: Phase) -> None:
        self.phase = phase
        self.changed.set()


async def think[T](
    message: discord.Message,
    work: Coroutine[Any, Any, T],
    *,
    after: float = THINKING_AFTER_SECONDS,
) -> tuple[T, discord.Message | None]:
    """Run ``work`` under the typing indicator, posting and updating a placeholder reply to
    ``message`` that tracks the turn's phase (see the module docstring).

    Returns ``work``'s result and the placeholder (``None`` if none was posted), which the
    caller passes to :func:`clear` after sending the answer. Only ``work`` itself (or a
    cancellation) can raise."""
    status = _Status()
    with observe(status.update):
        task = asyncio.ensure_future(work)
    typing = asyncio.create_task(_keep_typing(message.channel))
    loop = asyncio.get_running_loop()
    deadline = loop.time() + after
    placeholder: discord.Message | None = None
    # The phase the placeholder shows; None until one is (attempted to be) posted.
    shown: Phase | None = None
    try:
        while True:
            status.changed.clear()
            if task.done():
                break
            if shown is None:
                if status.phase is Phase.WAKING or loop.time() >= deadline:
                    shown = status.phase
                    placeholder = await _post_placeholder(message, _TEXT[shown])
                    # Sending a message clears the sender's typing indicator: restart the
                    # loop so it re-triggers now rather than at its next refresh.
                    typing.cancel()
                    typing = asyncio.create_task(_keep_typing(message.channel))
            elif placeholder is not None and shown is not status.phase:
                shown = status.phase
                await _edit_placeholder(placeholder, _TEXT[shown])
            changed = asyncio.ensure_future(status.changed.wait())
            timeout = max(0.0, deadline - loop.time()) if shown is None else None
            await asyncio.wait(
                {task, changed}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
            )
            changed.cancel()
        result = task.result()
    except BaseException:
        task.cancel()
        await clear(placeholder)
        raise
    finally:
        typing.cancel()
    return result, placeholder


async def _keep_typing(channel: discord.abc.Messageable) -> None:
    while True:
        try:
            await channel.typing()
        except Exception:
            logger.warning("couldn't trigger typing", exc_info=True)
        await asyncio.sleep(TYPING_REFRESH_SECONDS)


async def _post_placeholder(message: discord.Message, text: str) -> discord.Message | None:
    try:
        # Silent and non-pinging: it is a status line, not the answer.
        return await message.reply(text, mention_author=False, silent=True)
    except Exception:
        logger.warning("couldn't post the thinking placeholder", exc_info=True)
        return None


async def _edit_placeholder(placeholder: discord.Message, text: str) -> None:
    try:
        await placeholder.edit(content=text)
    except Exception:
        logger.warning("couldn't update the thinking placeholder", exc_info=True)


async def clear(placeholder: discord.Message | None) -> None:
    """Delete the placeholder :func:`think` posted, if any."""
    if placeholder is None:
        return
    try:
        await placeholder.delete()
    except Exception:
        logger.warning("couldn't delete the thinking placeholder", exc_info=True)
