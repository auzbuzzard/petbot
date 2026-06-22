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
        # Always unresolved, so the walk goes through `fetch_message` (the general path).
        self.message_id = message_id
        self.resolved = None


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


async def test_walk_collects_ancestors_newest_first() -> None:
    bot_msg = FakeMessage(author=FakeAuthor(1, "PetBot"), content="here you go!")
    user_msg = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> show me a pony", reference=FakeRef(100)
    )
    trigger = FakeMessage(
        author=FakeAuthor(2, "Alice"), content="<@1> another?", reference=FakeRef(101)
    )
    channel = FakeChannel({100: bot_msg, 101: user_msg})
    for msg in (bot_msg, user_msg, trigger):
        msg.channel = channel

    raw = await walk_reply_chain(trigger, bot_user_id=1, max_turns=25)  # type: ignore[arg-type]
    assert [(r.display_name, r.is_self) for r in raw] == [("Alice", False), ("PetBot", True)]


async def test_walk_respects_max_turns() -> None:
    parent = FakeMessage(author=FakeAuthor(1, "PetBot"), content="oldest")
    middle = FakeMessage(author=FakeAuthor(2, "Alice"), content="middle", reference=FakeRef(1))
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="newest", reference=FakeRef(2))
    channel = FakeChannel({1: parent, 2: middle})
    for msg in (parent, middle, trigger):
        msg.channel = channel

    raw = await walk_reply_chain(trigger, bot_user_id=1, max_turns=1)  # type: ignore[arg-type]
    assert len(raw) == 1 and raw[0].text == "middle"


async def test_walk_stops_on_unfetchable_ancestor() -> None:
    trigger = FakeMessage(author=FakeAuthor(2, "Alice"), content="hi", reference=FakeRef(999))
    trigger.channel = FakeChannel({})  # 999 missing -> NotFound -> stop, not raise
    assert await walk_reply_chain(trigger, bot_user_id=1, max_turns=25) == []  # type: ignore[arg-type]


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

    turns = await reconstruct(
        trigger,  # type: ignore[arg-type]
        bot_user_id=1,
        max_turns=25,
        strip_mention=_without_mention,
    )
    assert turns == (
        Turn(role=Role.ASSISTANT, author="PetBot", text="[image] results — http://i/x.png"),
    )


async def test_reconstruct_is_empty_without_a_reply() -> None:
    msg = FakeMessage(author=FakeAuthor(2, "Alice"), content="<@1> hi")
    turns = await reconstruct(
        msg,  # type: ignore[arg-type]
        bot_user_id=1,
        max_turns=25,
        strip_mention=_without_mention,
    )
    assert turns == ()
