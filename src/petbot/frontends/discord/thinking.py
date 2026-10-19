"""A Discord-native "thinking" state for a slow conversational turn.

Discord gives a plain message no built-in progress UI, whether it is a DM, an @mention or a
reply to PetBot (a slash command gets "PetBot is thinking…" from its deferred response).
The typing indicator is the first line of feedback: one trigger lasts ~10 s, so
:func:`think` re-triggers it every :data:`TYPING_REFRESH_SECONDS` for as long as the turn
runs. Past
:data:`THINKING_AFTER_SECONDS` a typing dot alone stops reading as "working on it", so
:func:`think` also posts a small placeholder reply (:data:`THINKING`, Discord ``-#``
subtext) and keeps typing. The caller retires the placeholder with :func:`clear` once the
real answer is sent, so the answer lands as a fresh message rather than an "(edited)" one.

Typing and the placeholder are cosmetic: any failure to trigger, post or delete them is
logged and never sinks the turn.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

import discord

logger = logging.getLogger(__name__)

#: When a turn earns a placeholder. Ten seconds is where a wait stops holding attention
#: (Nielsen's response-time limits) and is the life of one typing trigger. It also clears a
#: normal cold start of the core Lambda (~9 s end to end: ~3.4 s init plus the agent run).
#: So the placeholder shows for the waits that need it, chiefly an ``Inactive`` worker
#: re-activating (~20 s before the cold start even begins), and not for routine turns.
THINKING_AFTER_SECONDS = 10.0

#: How often to re-trigger typing: well inside one trigger's ~10 s life.
TYPING_REFRESH_SECONDS = 5.0

#: The placeholder: Discord subtext, so it reads as a status line, not an answer.
THINKING = "-# 💭 thinking… (waking up can take a little while)"


async def think[T](
    message: discord.Message,
    work: Coroutine[Any, Any, T],
    *,
    after: float = THINKING_AFTER_SECONDS,
) -> tuple[T, discord.Message | None]:
    """Run ``work`` under the typing indicator; if it outlasts ``after`` seconds, post the
    :data:`THINKING` placeholder as a reply to ``message`` and keep typing.

    Returns ``work``'s result and the placeholder (``None`` if the turn was quick), which
    the caller passes to :func:`clear` after sending the answer. Only ``work`` itself (or a
    cancellation) can raise."""
    task = asyncio.ensure_future(work)
    typing = asyncio.create_task(_keep_typing(message.channel))
    placeholder: discord.Message | None = None
    try:
        done, _ = await asyncio.wait({task}, timeout=after)
        if not done:
            placeholder = await _post_placeholder(message)
            # Sending a message clears the sender's typing indicator: restart the loop so it
            # re-triggers now rather than at its next refresh.
            typing.cancel()
            typing = asyncio.create_task(_keep_typing(message.channel))
        result = await task
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


async def _post_placeholder(message: discord.Message) -> discord.Message | None:
    try:
        # Silent and non-pinging: it is a status line, not the answer.
        return await message.reply(THINKING, mention_author=False, silent=True)
    except Exception:
        logger.warning("couldn't post the thinking placeholder", exc_info=True)
        return None


async def clear(placeholder: discord.Message | None) -> None:
    """Delete the placeholder :func:`think` posted, if any."""
    if placeholder is None:
        return
    try:
        await placeholder.delete()
    except Exception:
        logger.warning("couldn't delete the thinking placeholder", exc_info=True)
