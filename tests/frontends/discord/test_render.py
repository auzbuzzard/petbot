from __future__ import annotations

from typing import Literal

import discord
import pytest

from petbot.domain import (
    CommandInput,
    EmbedSpec,
    Platform,
    Process,
    Recalled,
    SkillContext,
    SkillResult,
    ToolCall,
)
from petbot.frontends.discord.bot import PetBot
from petbot.frontends.discord.context import build_context, build_interaction_context
from petbot.frontends.discord.render import (
    SERVICE_UNREACHABLE,
    respond,
    respond_interaction,
    to_embed,
    unwrap_markup,
)
from petbot.frontends.discord.settings import DiscordSettings, HttpService
from petbot.frontends.discord.slash import (
    _as_app_command,
    _option_type,
    _with_defer,
    build_commands,
)
from petbot.frontends.discord.text import chunk_text
from petbot.types import CATALOG


class FakeChannel:
    def __init__(self, *, nsfw: bool = False, channel_id: int = 99) -> None:
        self.id = channel_id
        self._nsfw = nsfw
        self.sent: list[dict[str, object]] = []
        self.kwargs: list[dict[str, object]] = []

    def is_nsfw(self) -> bool:
        return self._nsfw

    async def send(
        self,
        content: str | None = None,
        embed: discord.Embed | None = None,
        *,
        reference: object = None,
        mention_author: bool | None = None,
    ) -> None:
        self.sent.append({"content": content, "embed": embed})
        self.kwargs.append({"reference": reference, "mention_author": mention_author})


class FakeAuthor:
    def __init__(self) -> None:
        self.id = 7
        self.display_name = "Rex"
        self.bot = False


class FakeGuild:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeMessage:
    def __init__(self, channel: FakeChannel, guild: FakeGuild | None = None) -> None:
        self.author = FakeAuthor()
        self.channel = channel
        self.guild = guild


def test_unwrap_markup_strips_code_ticks_from_discord_timestamps() -> None:
    assert unwrap_markup("It's `<t:1792385094:t>` now") == "It's <t:1792385094:t> now"
    assert unwrap_markup("`<t:1792385094>` and `<t:5:R>`") == "<t:1792385094> and <t:5:R>"
    assert unwrap_markup("run `ls -la` or `<t:x:t>`") == "run `ls -la` or `<t:x:t>`"


def test_unwrap_markup_strips_code_ticks_from_a_lone_link_only() -> None:
    assert unwrap_markup("here: `https://leetcode.com/problems/two-sum/`") == (
        "here: https://leetcode.com/problems/two-sum/"
    )
    assert unwrap_markup("`<https://a.test/x>`") == "<https://a.test/x>"
    assert unwrap_markup("run `curl https://a.test`") == "run `curl https://a.test`"


async def test_respond_renders_a_code_wrapped_timestamp() -> None:
    channel = FakeChannel()
    await respond(channel, SkillResult.message("It's `<t:1:t>`!"))  # type: ignore[arg-type]
    assert channel.sent == [{"content": "It's <t:1:t>!", "embed": None}]


def test_to_embed_maps_fields() -> None:
    embed = to_embed(EmbedSpec(title="t", description="d", color=0xFF0000, image_url="http://i/x"))
    assert embed.title == "t"
    assert embed.description == "d"
    assert embed.image.url == "http://i/x"


async def test_respond_sends_text_only() -> None:
    channel = FakeChannel()
    await respond(channel, SkillResult.message("nope"))  # type: ignore[arg-type]
    assert channel.sent == [{"content": "nope", "embed": None}]


async def test_respond_never_posts_a_reported_trajectory() -> None:
    channel = FakeChannel()
    call = ToolCall(tool="math", args={"expression": "6*7"}, outcome="returned", output="42")
    await respond(channel, SkillResult(text="42!", trajectory=(call,)))  # type: ignore[arg-type]
    assert channel.sent == [{"content": "42!", "embed": None}]


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


async def test_respond_threads_reply_on_first_chunk_only() -> None:
    channel = FakeChannel()
    parent = object()
    await respond(channel, SkillResult.message("x" * 4500), reference=parent)  # type: ignore[arg-type]
    assert channel.kwargs[0] == {"reference": parent, "mention_author": False}
    assert channel.kwargs[1] == {"reference": None, "mention_author": None}


def test_build_context_reads_nsfw_and_ids() -> None:
    nsfw = build_context(FakeMessage(FakeChannel(nsfw=True, channel_id=5)))  # type: ignore[arg-type]
    assert nsfw.platform is Platform.DISCORD
    assert nsfw.allows_explicit is True
    assert nsfw.conversation_id == "discord:5"
    assert nsfw.user.display_name == "Rex"
    sfw = build_context(FakeMessage(FakeChannel(nsfw=False)))  # type: ignore[arg-type]
    assert sfw.allows_explicit is False


def test_build_context_carries_server_and_channel_names() -> None:
    channel = FakeChannel()
    channel.name = "general"  # type: ignore[attr-defined]
    ctx = build_context(FakeMessage(channel, FakeGuild("Hyena Den")))  # type: ignore[arg-type]
    assert (ctx.community_name, ctx.channel_name) == ("Hyena Den", "general")
    dm = build_context(FakeMessage(FakeChannel()))  # type: ignore[arg-type]
    assert (dm.community_name, dm.channel_name) == (None, None)


class _RaisingProcess(Process):
    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        raise RuntimeError("service unreachable")


async def test_mention_maps_transport_error_to_friendly_result() -> None:
    bot = PetBot(DiscordSettings(discord_token="x", service=HttpService(url="http://svc/dispatch")))
    bot.process = _RaisingProcess()
    result = await bot._respond("hello", FakeMessage(FakeChannel()), Recalled())  # type: ignore[arg-type]
    assert result.text == SERVICE_UNREACHABLE


class FakeResponse:
    def __init__(self) -> None:
        self.deferred = False

    async def defer(self) -> None:
        self.deferred = True


class FakeFollowup:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []

    async def send(self, content: str | None = None, embed: discord.Embed | None = None) -> None:
        self.sent.append({"content": content, "embed": embed})


class FakeInteraction:
    def __init__(self, *, nsfw: bool = False, channel_id: int = 99) -> None:
        self.user = FakeAuthor()
        self.channel = FakeChannel(nsfw=nsfw, channel_id=channel_id)
        self.channel_id = channel_id
        self.response = FakeResponse()
        self.followup = FakeFollowup()


def test_build_interaction_context_reads_nsfw_and_ids() -> None:
    ctx = build_interaction_context(FakeInteraction(nsfw=True, channel_id=8))  # type: ignore[arg-type]
    assert ctx.platform is Platform.DISCORD
    assert ctx.allows_explicit is True
    assert ctx.conversation_id == "discord:8"
    assert ctx.user.display_name == "Rex"
    sfw = build_interaction_context(FakeInteraction(nsfw=False))  # type: ignore[arg-type]
    assert sfw.allows_explicit is False


def test_slash_surface_skips_agent_only_tools() -> None:
    names = {c.name for c in build_commands(_RaisingProcess())}
    assert names == {"math", "derpi", "e621", "leetcode"}


async def test_respond_interaction_sends_card_as_followup() -> None:
    interaction = FakeInteraction()
    result = SkillResult.message("here", embed=EmbedSpec(title="c", image_url="http://i/x"))
    await respond_interaction(interaction, result)  # type: ignore[arg-type]
    assert interaction.followup.sent[0]["content"] == "here"
    assert interaction.followup.sent[0]["embed"] is not None


class _StubProcess(Process):
    def __init__(self) -> None:
        self.received: list[CommandInput] = []

    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        assert isinstance(inp, CommandInput)
        self.received.append(inp)
        return SkillResult.message(f"{inp.name} ok")


async def test_with_defer_acks_before_delegating() -> None:
    seen: dict[str, object] = {}

    async def handle(interaction: FakeInteraction, **values: object) -> None:
        seen["deferred_first"] = interaction.response.deferred
        seen["values"] = values

    await _with_defer(handle)(FakeInteraction(), expression="6*7")
    assert seen["deferred_first"] is True
    assert seen["values"] == {"expression": "6*7"}


async def test_slash_command_dispatches_a_command_input_and_followups() -> None:
    process = _StubProcess()
    math = next(c for c in build_commands(process) if c.name == "math")
    interaction = FakeInteraction()
    await math.callback(interaction, expression="6*7")  # type: ignore[arg-type, call-arg]
    assert interaction.response.deferred is True
    assert process.received[0].name == "math"
    assert process.received[0].values == {"expression": "6*7"}
    assert interaction.followup.sent[0]["content"] == "math ok"


async def test_slash_command_maps_failure_to_friendly_followup() -> None:
    e621 = next(c for c in build_commands(_RaisingProcess()) if c.name == "e621")
    interaction = FakeInteraction()
    await e621.callback(interaction, tags="fox")  # type: ignore[arg-type, call-arg]
    assert interaction.response.deferred is True
    assert interaction.followup.sent[0]["content"] == SERVICE_UNREACHABLE


def test_slash_command_options_are_generated_from_args_model() -> None:
    spec = next(s for s in CATALOG if s.name == "e621")

    async def _noop(interaction: object, **values: object) -> None: ...

    command = _as_app_command(spec, _noop)
    assert command.name == "e621"
    params = command._params
    assert set(params) == set(spec.args_model.model_fields)
    assert params["tags"].required is True
    assert params["sort"].required is False
    assert str(params["min_score"].description) == "Minimum score floor."


def test_slash_literal_options_become_choices() -> None:
    spec = next(s for s in CATALOG if s.name == "leetcode")

    async def _noop(interaction: object, **values: object) -> None: ...

    params = _as_app_command(spec, _noop)._params
    assert params["mode"].required is True
    assert [c.value for c in params["mode"].choices] == ["daily", "random"]
    assert params["difficulty"].required is False
    assert [c.value for c in params["difficulty"].choices] == ["easy", "medium", "hard"]


def test_slash_rejects_a_non_string_literal() -> None:
    assert _option_type(Literal["a", "b"] | None) == Literal["a", "b"]
    with pytest.raises(TypeError):
        _option_type(Literal[1, 2])
