"""Reconstructing conversation history from the Discord reply chain.

The pure mapping (`to_turns`) is tested directly; the walk is tested against fake
messages whose parents are served through a fake channel's `fetch_message`.
"""

from __future__ import annotations

from collections.abc import Mapping

import discord

from petbot.domain import Role, Turn
from petbot.frontends.discord.bot import _without_mention
from petbot.frontends.discord.history import (
    RawTurn,
    _describe_card,
    reconstruct,
    resolve_parent,
    to_turns,
    walk_reply_chain,
)


class _FakeResp:
    status = 404
    reason = "Not Found"


class FakeAuthor:
    def __init__(self, author_id: int, name: str) -> None:
        self.id = author_id
        self.display_name = name


class FakeRef:
    def __init__(self, message_id: int | None) -> None:
        # Always unresolved + uncached, so resolution goes through `fetch_message`.
        self.message_id = message_id
        self.resolved = None
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


# --- the pure mapping ---------------------------------------------------------


def test_to_turns_orders_oldest_first_and_maps_roles() -> None:
    raw = [  # walk yields newest-first
        RawTurn(display_name="Alice", is_self=False, text="<@1> and another?"),
        RawTurn(display_name="PetBot", is_self=True, text="here you go!"),
    ]
    assert to_turns(raw, bot_user_id=1, strip_mention=_without_mention) == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="here you go!"),
        Turn(role=Role.USER, author="Alice", text="and another?"),
    )


def test_to_turns_drops_turns_that_become_empty() -> None:
    raw = [
        RawTurn(display_name="Alice", is_self=False, text="<@1>"),  # only a mention
        RawTurn(display_name="PetBot", is_self=True, text="   "),
    ]
    assert to_turns(raw, bot_user_id=1, strip_mention=_without_mention) == ()


def test_describe_card_uses_title_and_image() -> None:
    embed = discord.Embed(title="results")
    embed.set_image(url="http://i/x.png")
    assert _describe_card(embed) == "[image] results — http://i/x.png"
    assert _describe_card(discord.Embed()) == ""


# --- the walk -----------------------------------------------------------------


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


async def test_walk_collects_ancestors_newest_first() -> None:
    bot_msg = FakeMessage(author=FakeAuthor(1, "PetBot"), content="here you go!")
    user_msg = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> show me a pony", reference=FakeRef(100)
    )
    channel = FakeChannel({100: bot_msg})
    for msg in (bot_msg, user_msg):
        msg.channel = channel

    # The caller passes the already-resolved immediate parent (`user_msg`).
    raw = await walk_reply_chain(user_msg, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    assert [(r.display_name, r.is_self) for r in raw] == [("Alice", False), ("PetBot", True)]


async def test_walk_respects_max_turns() -> None:
    oldest = FakeMessage(author=FakeAuthor(1, "PetBot"), content="oldest")
    middle = FakeMessage(author=FakeAuthor(2, "Alice"), content="middle", reference=FakeRef(1))
    channel = FakeChannel({1: oldest})
    for msg in (oldest, middle):
        msg.channel = channel

    raw = await walk_reply_chain(middle, bot_user_id=1, max_turns=1)  # type: ignore[arg-type]
    assert len(raw) == 1 and raw[0].text == "middle"


async def test_walk_stops_on_unfetchable_ancestor() -> None:
    # The parent is recorded; its own parent (999) is missing -> the walk stops, not raises.
    parent = FakeMessage(author=FakeAuthor(1, "PetBot"), content="hi", reference=FakeRef(999))
    parent.channel = FakeChannel({})
    raw = await walk_reply_chain(parent, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    assert [r.text for r in raw] == ["hi"]


# --- end to end ---------------------------------------------------------------


async def test_reconstruct_flattens_an_image_only_bot_card() -> None:
    card = discord.Embed(title="results")
    card.set_image(url="http://i/x.png")
    bot_card = FakeMessage(author=FakeAuthor(1, "PetBot"), content="", embeds=(card,))
    trigger = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> another?", reference=FakeRef(100)
    )
    channel = FakeChannel({100: bot_card})
    bot_card.channel = trigger.channel = channel

    parent = await resolve_parent(trigger)  # type: ignore[arg-type]
    turns = await reconstruct(
        parent,
        bot_user_id=1,
        max_turns=25,
        strip_mention=_without_mention,
    )
    assert turns == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="[image] results — http://i/x.png"),
    )


async def test_reconstruct_is_empty_without_a_reply() -> None:
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> hi")
    parent = await resolve_parent(msg)  # type: ignore[arg-type]
    turns = await reconstruct(
        parent,
        bot_user_id=1,
        max_turns=25,
        strip_mention=_without_mention,
    )
    assert turns == ()
