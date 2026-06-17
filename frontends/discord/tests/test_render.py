"""The edge's pure rendering: EmbedSpec -> discord.Embed, result -> messages."""

from __future__ import annotations

import discord

from petbot.discord.context import build_context
from petbot.discord.render import respond, to_embed
from petbot.discord.text import chunk_text
from petbot.domain import EmbedSpec, Platform, SkillResult


class FakeChannel:
    """Captures what the renderer would send, without a gateway."""

    def __init__(self, *, nsfw: bool = False, channel_id: int = 99) -> None:
        self.id = channel_id
        self._nsfw = nsfw
        self.sent: list[dict[str, object]] = []

    def is_nsfw(self) -> bool:
        return self._nsfw

    async def send(self, content: str | None = None, embed: discord.Embed | None = None) -> None:
        self.sent.append({"content": content, "embed": embed})


class FakeAuthor:
    def __init__(self) -> None:
        self.id = 7
        self.display_name = "Rex"
        self.bot = False


class FakeMessage:
    def __init__(self, channel: FakeChannel) -> None:
        self.author = FakeAuthor()
        self.channel = channel


def test_to_embed_maps_fields() -> None:
    embed = to_embed(EmbedSpec(title="t", description="d", color=0xFF0000, image_url="http://i/x"))
    assert embed.title == "t"
    assert embed.description == "d"
    assert embed.image.url == "http://i/x"


async def test_respond_sends_error_as_plain_message() -> None:
    channel = FakeChannel()
    await respond(channel, SkillResult.failure("nope"))  # type: ignore[arg-type]
    assert channel.sent == [{"content": "nope", "embed": None}]


async def test_respond_sends_text_then_embed_on_first_chunk() -> None:
    channel = FakeChannel()
    result = SkillResult.message("hello", embed=EmbedSpec(title="card"))
    await respond(channel, result)  # type: ignore[arg-type]
    assert len(channel.sent) == 1
    assert channel.sent[0]["content"] == "hello"
    assert channel.sent[0]["embed"] is not None


async def test_respond_chunks_long_text_embed_only_first() -> None:
    channel = FakeChannel()
    long = "x" * 4500
    await respond(channel, SkillResult.message(long, embed=EmbedSpec(title="c")))  # type: ignore[arg-type]
    assert len(channel.sent) == len(chunk_text(long))
    assert channel.sent[0]["embed"] is not None
    assert channel.sent[1]["embed"] is None


def test_build_context_reads_nsfw_and_ids() -> None:
    nsfw = build_context(FakeMessage(FakeChannel(nsfw=True, channel_id=5)))  # type: ignore[arg-type]
    assert nsfw.platform is Platform.DISCORD
    assert nsfw.allows_explicit is True
    assert nsfw.conversation_id == "discord:5"
    assert nsfw.user.display_name == "Rex"
    sfw = build_context(FakeMessage(FakeChannel(nsfw=False)))  # type: ignore[arg-type]
    assert sfw.allows_explicit is False
