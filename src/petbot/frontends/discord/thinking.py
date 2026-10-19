"""A Discord-native "thinking" state for a slow conversational turn.

Discord gives an @mention no built-in progress UI (a slash command gets "PetBot is
thinking…" from its deferred response; a message gets nothing). The typing indicator is the
first line of feedback: it lasts ~10 s per trigger, so discord.py re-triggers it every 5 s
for as long as the turn runs. Past :data:`THINKING_AFTER_SECONDS` a typing dot alone stops
reading as "working on it", so :func:`think` also posts a small placeholder reply
(:data:`THINKING`, Discord ``-#`` subtext) and keeps typing. The caller retires the
placeholder with :func:`clear` once the real answer is sent, so the answer lands as a
fresh message rather than an "(edited)" one.

The placeholder is cosmetic: failing to post or delete it is logged and never sinks the
turn.
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
    the caller passes to :func:`clear` after sending the answer."""
    task = asyncio.ensure_future(work)
    placeholder: discord.Message | None = None
    try:
        async with message.channel.typing():
            done, _ = await asyncio.wait({task}, timeout=after)
            if not done:
                placeholder = await _post_placeholder(message)
            result = await task
    except BaseException:
        task.cancel()
        await clear(placeholder)
        raise
    return result, placeholder


async def _post_placeholder(message: discord.Message) -> discord.Message | None:
    try:
        # Silent and non-pinging: it is a status line, not the answer.
        placeholder = await message.reply(THINKING, mention_author=False, silent=True)
    except discord.HTTPException:
        logger.warning("couldn't post the thinking placeholder", exc_info=True)
        return None
    try:
        # Sending a message clears the sender's typing indicator; re-trigger it now rather
        # than leave a gap until discord.py's next 5 s refresh.
        await message.channel.typing()
    except discord.HTTPException:
        logger.warning("couldn't re-trigger typing", exc_info=True)
    return placeholder


async def clear(placeholder: discord.Message | None) -> None:
    """Delete the placeholder :func:`think` posted, if any."""
    if placeholder is None:
        return
    try:
        await placeholder.delete()
    except discord.HTTPException:
        logger.warning("couldn't delete the thinking placeholder", exc_info=True)
