"""Reconstruct a conversation's history from the Discord reply chain.

The frontend is the only place that holds the gateway, so it is the only place that can
walk ``message.reference`` to recover the turns a reply continues. This maps that chain
onto neutral :class:`~petbot.domain.input.Turn` values for ``TextInput.history`` — the
driving-adapter half of "map a platform event to a complete ``Input``".

Three parts: :func:`resolve_parent` (one message → the message it replies to, preferring
a copy Discord already gave us over a REST fetch), an async :func:`walk_reply_chain` that
follows it up the chain (bounded, tolerant of deleted/unreadable ancestors), and a pure
:func:`to_turns` that maps the gathered Discord turns to neutral ones. The history is shipped
*faithful and untrimmed* — an
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
class DiscordTurn:
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


async def resolve_parent(message: discord.Message) -> discord.Message | None:
    """The message ``message`` replies to, or ``None`` if it isn't a reply (or the parent
    was deleted — a ``NotFound`` is the reply chain's natural end).

    Prefers a copy Discord already handed us (inline ``resolved``, then ``cached_message``)
    and only pays for a REST ``fetch_message`` when neither has it. A permission
    (``Forbidden``) or transient error is **not** swallowed here — it propagates to the
    one reconstruction boundary (``PetBot._reply_context``), which logs it and degrades to
    no memory (ADR 0009: errors are raised, handled once at a boundary).
    """
    ref = message.reference
    if ref is None or ref.message_id is None:
        return None
    if isinstance(ref.resolved, discord.DeletedReferencedMessage):
        return None
    free = ref.resolved if isinstance(ref.resolved, discord.Message) else ref.cached_message
    if free is not None:
        return free
    try:
        return await message.channel.fetch_message(ref.message_id)
    except discord.NotFound:
        return None


async def walk_reply_chain(
    parent: discord.Message | None, *, bot_user_id: int, max_turns: int
) -> list[DiscordTurn]:
    """Walk the reply chain from ``parent`` upward (newest-first), up to ``max_turns``.

    ``parent`` is the message the current one replies to (``None`` when it isn't a reply),
    already resolved by the caller so the immediate parent is fetched only once. It stops
    at the chain's end or a deleted ancestor (``resolve_parent`` returns ``None``); a
    permission/transient error propagates to the reconstruction boundary, not swallowed.
    """
    raw: list[DiscordTurn] = []
    current = parent
    while current is not None and len(raw) < max_turns:
        raw.append(
            DiscordTurn(
                display_name=current.author.display_name,
                is_self=current.author.id == bot_user_id,
                text=_message_text(current),
            )
        )
        current = await resolve_parent(current)
    return raw


def to_turns(
    raw: list[DiscordTurn],
    *,
    bot_user_id: int,
    strip_mention: Callable[[str, int], str],
) -> tuple[Turn, ...]:
    """Map gathered Discord turns (newest-first) to neutral turns (oldest-first).

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
    parent: discord.Message | None,
    *,
    bot_user_id: int,
    max_turns: int,
    strip_mention: Callable[[str, int], str],
) -> tuple[Turn, ...]:
    """Walk the reply chain from ``parent`` and map it to neutral history (oldest-first)."""
    raw = await walk_reply_chain(parent, bot_user_id=bot_user_id, max_turns=max_turns)
    return to_turns(raw, bot_user_id=bot_user_id, strip_mention=strip_mention)
