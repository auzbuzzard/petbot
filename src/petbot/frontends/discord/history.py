"""Reconstruct a conversation's history from the Discord reply chain.

The frontend is the only place that holds the gateway, so it is the only place that can
walk ``message.reference`` to recover the turns a reply continues. This maps that chain
onto neutral :class:`~petbot.domain.input.Turn` values for ``TextInput.history`` — the
driving-adapter half of "map a platform event to a complete ``Input``".

Two parts: an async :func:`walk_reply_chain` that does the Discord I/O (bounded, and
tolerant of deleted/unreadable ancestors), and a pure :func:`to_turns` that maps the
gathered raw turns to neutral ones. The history is shipped *faithful and untrimmed* — an
over-long conversation is handled compute-side (reactively), not here. An image-only bot
card is flattened to a faithful text description (its real title + image URL), since an
assistant turn can only be text in the model's history.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import discord

from petbot.domain import Role, Turn


@dataclass(frozen=True, slots=True)
class RawTurn:
    """One ancestor message, read off Discord, before neutral mapping."""

    display_name: str
    is_self: bool
    text: str


def _describe_card(embed: discord.Embed) -> str:
    """A faithful one-line description of an embed (title + image URL), or ``""``."""
    parts = [part for part in (embed.title, embed.image.url) if part]
    return f"[image] {' — '.join(parts)}" if parts else ""


def _message_text(message: discord.Message) -> str:
    """A message's text: its content, else a description of its first usable embed."""
    if message.content:
        return message.content
    for embed in message.embeds:
        described = _describe_card(embed)
        if described:
            return described
    return ""


async def walk_reply_chain(
    message: discord.Message, *, bot_user_id: int, max_turns: int
) -> list[RawTurn]:
    """Walk ``message``'s reply ancestors (newest-first), up to ``max_turns``.

    Excludes ``message`` itself (it is the current prompt). Stops — without raising — at
    the chain's end, a deleted ancestor, or one that can't be fetched.
    """
    channel = message.channel
    raw: list[RawTurn] = []
    current = message
    for _ in range(max_turns):
        ref = current.reference
        if ref is None or ref.message_id is None:
            break
        resolved = ref.resolved
        if isinstance(resolved, discord.Message):
            parent = resolved
        elif isinstance(resolved, discord.DeletedReferencedMessage):
            break
        else:
            try:
                parent = await channel.fetch_message(ref.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                break
        raw.append(
            RawTurn(
                display_name=parent.author.display_name,
                is_self=parent.author.id == bot_user_id,
                text=_message_text(parent),
            )
        )
        current = parent
    return raw


def to_turns(
    raw: list[RawTurn],
    *,
    bot_user_id: int,
    strip_mention: Callable[[str, int], str],
) -> tuple[Turn, ...]:
    """Map gathered raw turns (newest-first) to neutral turns (oldest-first).

    A turn PetBot authored is an assistant turn; everything else is a user turn, with the
    bot's own mention stripped (``strip_mention``). Empty turns are dropped.
    """
    turns: list[Turn] = []
    for entry in reversed(raw):
        if entry.is_self:
            role, text = Role.ASSISTANT, entry.text.strip()
        else:
            role, text = Role.USER, strip_mention(entry.text, bot_user_id).strip()
        if text:
            turns.append(Turn(role=role, author=entry.display_name, text=text))
    return tuple(turns)


async def reconstruct(
    message: discord.Message,
    *,
    bot_user_id: int,
    max_turns: int,
    strip_mention: Callable[[str, int], str],
) -> tuple[Turn, ...]:
    """Walk the reply chain and map it to neutral history (oldest-first)."""
    raw = await walk_reply_chain(message, bot_user_id=bot_user_id, max_turns=max_turns)
    return to_turns(raw, bot_user_id=bot_user_id, strip_mention=strip_mention)
