"""Reconstruct a conversation's history from the Discord reply chain.

The frontend holds the gateway, so it is the only place that can walk ``message.reference``
to recover the turns a reply continues, mapping them onto neutral
:class:`~petbot.domain.input.Turn` values for ``TextInput.history`` — the driving-adapter
half of "map a platform event to a complete ``Input``".

The walk is an async *unfold* of the reply chain (:func:`aiter_until_none` over
:func:`resolve_parent`), bounded by :func:`atake`, then mapped by the pure :func:`to_turns`.
:func:`resolve_parent` **raises** on an unreadable hop (e.g. a missing ``Read Message
History`` permission) rather than swallowing it — the error unwinds to the single
reconstruction boundary (``PetBot._reply_context``), which turns it into an ``Unrecalled``
history so the agent is told it lost the thread instead of answering blind (ADR 0009: errors
are raised, handled once at a boundary). An image-only bot card is flattened to a faithful
text description (its real title + image URL), since an assistant turn can only be text in
the model's history.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import discord

from petbot.domain import Role, Turn


def strip_self_mention(content: str, bot_user_id: int) -> str:
    """Remove only this bot's mention (``<@id>`` / ``<@!id>``), leaving others intact."""
    return re.sub(rf"<@!?{bot_user_id}>", "", content)


# --- async iteration the stdlib doesn't ship (no 2-arg ``aiter``, no async ``islice``) ----


async def aiter_until_none[T](
    step: Callable[[T], Awaitable[T | None]], start: T
) -> AsyncIterator[T]:
    """Async unfold: yield ``step(start)``, ``step(step(start))``… until ``step`` returns
    ``None``. ``step``'s exceptions propagate, short-circuiting the stream.

    (The async equivalent of ``iter(callable, sentinel)`` that feeds each result back as the
    next seed — which ``aiter`` has no two-argument form for.)"""
    node = await step(start)
    while node is not None:
        yield node
        node = await step(node)


async def atake[T](n: int, it: AsyncIterator[T]) -> AsyncIterator[T]:
    """Yield at most the first ``n`` items of ``it`` — the async ``islice`` the stdlib lacks.

    Pulls exactly ``n`` items (never an extra), so a bounded reply-chain walk fetches no more
    ancestors than asked for."""
    if n <= 0:
        return
    count = 0
    async for item in it:
        yield item
        count += 1
        if count >= n:
            return


# --- reading the reply chain --------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DiscordTurn:
    """One ancestor message, read off Discord, before neutral mapping."""

    display_name: str
    is_self: bool
    text: str

    @classmethod
    def of(cls, message: discord.Message, bot_user_id: int) -> DiscordTurn:
        return cls(
            display_name=message.author.display_name,
            is_self=message.author.id == bot_user_id,
            text=_message_text(message),
        )


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


def replying_to_self(message: discord.Message, bot_user_id: int) -> bool:
    """Whether ``message`` replies to one of the bot's own messages — read only from the copy
    Discord inlined (``reference.resolved``), never a fetch, so the conversational trigger
    can't fail on a missing permission (a reply-to-self that wasn't inlined just needs an
    @mention, like any other message)."""
    ref = message.reference
    resolved = ref.resolved if ref is not None else None
    if resolved is None or isinstance(resolved, discord.DeletedReferencedMessage):
        return False
    return resolved.author.id == bot_user_id


def is_conversational_trigger(message: discord.Message, bot_user_id: int) -> bool:
    """Whether ``message`` should start or continue a conversation with PetBot.

    A DM is always addressed to the bot, so every DM triggers with no @mention. In a guild
    it takes an explicit @mention or a reply to one of the bot's own messages (a follow-up
    needs no re-mention). ``message.guild is None`` is the DM discriminator."""
    if message.guild is None:
        return True
    mentioned = any(user.id == bot_user_id for user in message.mentions)
    return mentioned or replying_to_self(message, bot_user_id)


async def resolve_parent(message: discord.Message) -> discord.Message | None:
    """The valid parent ``message`` replies to, or ``None`` if it isn't a reply or the parent
    was deleted (a ``NotFound`` is the reply chain's natural end).

    Prefers a copy Discord already handed us (inline ``resolved``, then ``cached_message``)
    and only pays for a REST ``fetch_message`` when neither has it. A permission
    (``Forbidden``) or transient (``HTTPException``) error is **not** swallowed here — it
    propagates to the one reconstruction boundary (``PetBot._reply_context``), which logs it
    and degrades to ``Unrecalled`` (ADR 0009: errors are raised, handled once at a boundary).
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


def to_turns(raw: list[DiscordTurn], *, bot_user_id: int) -> tuple[Turn, ...]:
    """Map gathered Discord turns (newest-first) to neutral turns (oldest-first).

    A turn PetBot authored is an assistant turn; everything else is a user turn, with the
    bot's own mention stripped. Empty turns are dropped."""
    turns: list[Turn] = []
    for entry in reversed(raw):
        if entry.is_self:
            role, text = Role.ASSISTANT, entry.text.strip()
        else:
            role, text = Role.USER, strip_self_mention(entry.text, bot_user_id).strip()
        if text:
            turns.append(Turn(role=role, author=entry.display_name, text=text))
    return tuple(turns)


async def reconstruct(
    message: discord.Message, *, bot_user_id: int, max_turns: int
) -> tuple[Turn, ...]:
    """Walk the reply chain from ``message`` (bounded by ``max_turns``) and map it to neutral
    history, oldest-first: ``take(max_turns, unfold(resolve_parent, message))``, then
    :func:`to_turns`. Raises on an unreadable hop — handled at the reconstruction boundary."""
    chain = atake(max_turns, aiter_until_none(resolve_parent, message))
    raw = [DiscordTurn.of(parent, bot_user_id) async for parent in chain]
    return to_turns(raw, bot_user_id=bot_user_id)
