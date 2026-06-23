"""Reconstructing conversation history from the Discord reply chain.

The generic async combinators (`aiter_until_none`, `atake`) and the pure mapping (`to_turns`)
are tested directly; the walk is tested against fake messages whose parents are served through
a fake channel's `fetch_message`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping

import discord
import pytest

from petbot.domain import Role, Turn
from petbot.frontends.discord.history import (
    DiscordTurn,
    _describe_card,
    aiter_until_none,
    atake,
    reconstruct,
    replying_to_self,
    resolve_parent,
    strip_self_mention,
    to_turns,
)


class _FakeResp:
    status = 404
    reason = "Not Found"


class _ForbiddenResp:
    status = 403
    reason = "Forbidden"


class ForbiddenChannel:
    """A channel whose fetch is denied — stands in for a missing 'Read Message History'."""

    async def fetch_message(self, message_id: int) -> object:
        raise discord.Forbidden(_ForbiddenResp(), "missing access")  # type: ignore[arg-type]


class FakeAuthor:
    def __init__(self, author_id: int, name: str) -> None:
        self.id = author_id
        self.display_name = name


class FakeRef:
    def __init__(self, message_id: int | None, *, resolved: object = None) -> None:
        # `resolved` defaults to None (uncached) so resolution goes through `fetch_message`;
        # a test can inline a copy to exercise the no-fetch path.
        self.message_id = message_id
        self.resolved = resolved
        self.cached_message = None


class FakeChannel:
    def __init__(self, fetch: Mapping[int, FakeMessage] | None = None) -> None:
        self._fetch = dict(fetch or {})

    async def fetch_message(self, message_id: int) -> FakeMessage:
        if message_id not in self._fetch:
            raise discord.NotFound(_FakeResp(), "missing")  # type: ignore[arg-type]
        return self._fetch[message_id]


class FakeMessage:
    def __init__(
        self,
        *,
        author: FakeAuthor,
        content: str = "",
        embeds: tuple[discord.Embed, ...] = (),
        reference: FakeRef | None = None,
        channel: FakeChannel | None = None,
    ) -> None:
        self.author = author
        self.content = content
        self.embeds = list(embeds)
        self.reference = reference
        self.channel = channel or FakeChannel()


# --- generic async combinators ------------------------------------------------


async def test_aiter_until_none_unfolds_feeding_each_result_back() -> None:
    async def step(n: int) -> int | None:
        return n - 1 if n > 0 else None

    assert [x async for x in aiter_until_none(step, 3)] == [2, 1, 0]


async def test_aiter_until_none_propagates_step_errors() -> None:
    async def boom(_: int) -> int | None:
        raise RuntimeError("nope")

    with pytest.raises(RuntimeError):
        [x async for x in aiter_until_none(boom, 1)]


async def test_atake_yields_at_most_n_and_pulls_no_more() -> None:
    pulled = 0

    async def naturals() -> AsyncIterator[int]:
        nonlocal pulled
        i = 0
        while True:
            pulled += 1
            yield i
            i += 1

    assert [x async for x in atake(2, naturals())] == [0, 1]
    assert pulled == 2  # exactly n items pulled, never an extra
    assert [x async for x in atake(0, naturals())] == []


# --- the pure mapping ---------------------------------------------------------


def test_strip_self_mention_strips_only_this_bot() -> None:
    assert strip_self_mention("<@1> hi <@2>", 1) == " hi <@2>"
    assert strip_self_mention("<@!1> yo", 1) == " yo"


def test_to_turns_orders_oldest_first_and_maps_roles() -> None:
    raw = [  # walk yields newest-first
        DiscordTurn(display_name="Alice", is_self=False, text="<@1> and another?"),
        DiscordTurn(display_name="PetBot", is_self=True, text="here you go!"),
    ]
    assert to_turns(raw, bot_user_id=1) == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="here you go!"),
        Turn(role=Role.USER, author="Alice", text="and another?"),
    )


def test_to_turns_drops_turns_that_become_empty() -> None:
    raw = [
        DiscordTurn(display_name="Alice", is_self=False, text="<@1>"),  # only a mention
        DiscordTurn(display_name="PetBot", is_self=True, text="   "),
    ]
    assert to_turns(raw, bot_user_id=1) == ()


def test_describe_card_uses_title_and_image() -> None:
    embed = discord.Embed(title="results")
    embed.set_image(url="http://i/x.png")
    assert _describe_card(embed) == "[image] results — http://i/x.png"
    assert _describe_card(discord.Embed()) == ""


# --- the trigger predicate ----------------------------------------------------


def test_replying_to_self_reads_only_the_inlined_copy() -> None:
    bot_reply = FakeMessage(author=FakeAuthor(1, "PetBot"), content="hi")
    msg = FakeMessage(
        author=FakeAuthor(2, "Alice"),
        content="<@1> yo",
        reference=FakeRef(100, resolved=bot_reply),
    )
    assert replying_to_self(msg, 1) is True  # type: ignore[arg-type]
    assert replying_to_self(msg, 99) is False  # type: ignore[arg-type]  # not the bot
    # Not a reply, or no inlined copy -> False (no fetch, so the trigger can't fail).
    assert replying_to_self(FakeMessage(author=FakeAuthor(2, "Alice")), 1) is False  # type: ignore[arg-type]
    plain_reply = FakeMessage(author=FakeAuthor(2, "Alice"), reference=FakeRef(100))
    assert replying_to_self(plain_reply, 1) is False  # type: ignore[arg-type]


# --- resolving one hop --------------------------------------------------------


async def test_resolve_parent_fetches_when_unresolved() -> None:
    parent = FakeMessage(author=FakeAuthor(1, "PetBot"), content="here you go!")
    trigger = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> another?", reference=FakeRef(100)
    )
    trigger.channel = FakeChannel({100: parent})
    assert await resolve_parent(trigger) is parent  # type: ignore[arg-type, comparison-overlap]


async def test_resolve_parent_is_none_without_a_reference() -> None:
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="hi")
    assert await resolve_parent(msg) is None  # type: ignore[arg-type]


async def test_resolve_parent_is_none_when_unfetchable() -> None:
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="hi", reference=FakeRef(999))
    msg.channel = FakeChannel({})  # 999 missing -> NotFound -> None, not raised
    assert await resolve_parent(msg) is None  # type: ignore[arg-type]


async def test_resolve_parent_raises_on_forbidden() -> None:
    # A missing 'Read Message History' permission is NOT swallowed — it propagates to the
    # reconstruction boundary (ADR 0009: errors are raised, handled once).
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="hi", reference=FakeRef(500))
    msg.channel = ForbiddenChannel()  # type: ignore[assignment]
    with pytest.raises(discord.Forbidden):
        await resolve_parent(msg)  # type: ignore[arg-type]


# --- the bounded walk, end to end ---------------------------------------------


def _chained(*messages: FakeMessage) -> FakeChannel:
    """Wire a newest-first run of messages into one channel, each replying to the next, and
    return that channel. ``messages[0]`` is the trigger; each gets ``reference`` + fetch id."""
    channel = FakeChannel()
    for i, msg in enumerate(messages):
        msg.channel = channel
        if i + 1 < len(messages):
            msg.reference = FakeRef(i + 1)
            channel._fetch[i + 1] = messages[i + 1]
    return channel


async def test_reconstruct_walks_the_chain_oldest_first() -> None:
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> and another?")
    parent = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> show me a pony")
    grandparent = FakeMessage(author=FakeAuthor(1, "PetBot"), content="here you go!")
    _chained(trigger, parent, grandparent)
    turns = await reconstruct(trigger, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    # The trigger itself is excluded (it's the current prompt); ancestors come oldest-first.
    assert turns == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="here you go!"),
        Turn(role=Role.USER, author="Alice", text="show me a pony"),
    )


async def test_reconstruct_respects_max_turns() -> None:
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="trigger")
    newer = FakeMessage(author=FakeAuthor(2, "Alice"), content="newer")
    older = FakeMessage(author=FakeAuthor(1, "PetBot"), content="older")
    _chained(trigger, newer, older)
    turns = await reconstruct(trigger, bot_user_id=1, max_turns=1)  # type: ignore[arg-type]
    assert turns == (Turn(role=Role.USER, author="Alice", text="newer"),)


async def test_reconstruct_stops_on_a_deleted_ancestor() -> None:
    # The immediate parent is read; ITS parent (999) is gone -> the walk stops, not raises.
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> yo", reference=FakeRef(100))
    parent = FakeMessage(author=FakeAuthor(1, "PetBot"), content="hi", reference=FakeRef(999))
    channel = FakeChannel({100: parent})  # 999 missing -> NotFound -> None
    trigger.channel = parent.channel = channel
    turns = await reconstruct(trigger, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    assert turns == (Turn(role=Role.ASSISTANT, author="PetBot", text="hi"),)


async def test_reconstruct_propagates_a_forbidden_fetch() -> None:
    # The walk doesn't silently stop on a permission error — it propagates to the boundary.
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> yo", reference=FakeRef(500))
    trigger.channel = ForbiddenChannel()  # type: ignore[assignment]
    with pytest.raises(discord.Forbidden):
        await reconstruct(trigger, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]


async def test_reconstruct_flattens_an_image_only_bot_card() -> None:
    card = discord.Embed(title="results")
    card.set_image(url="http://i/x.png")
    trigger = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> another?", reference=FakeRef(100)
    )
    bot_card = FakeMessage(author=FakeAuthor(1, "PetBot"), content="", embeds=(card,))
    channel = FakeChannel({100: bot_card})
    trigger.channel = bot_card.channel = channel
    turns = await reconstruct(trigger, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    assert turns == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="[image] results — http://i/x.png"),
    )


async def test_reconstruct_is_empty_without_a_reply() -> None:
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> hi")
    assert await reconstruct(msg, bot_user_id=1, max_turns=25) == ()  # type: ignore[arg-type]
