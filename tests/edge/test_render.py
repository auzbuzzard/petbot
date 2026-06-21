"""The edge's pure rendering: EmbedSpec -> discord.Embed, result -> messages."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import discord

from petbot.domain import EmbedSpec, Platform, SkillResult
from petbot.edge.bot import PetBot, _without_mention
from petbot.edge.context import build_context, build_interaction_context
from petbot.edge.render import WORKER_UNREACHABLE, respond, respond_interaction, to_embed
from petbot.edge.settings import EdgeSettings, HttpWorker
from petbot.edge.slash import _as_app_command, _with_defer, build_commands
from petbot.edge.text import chunk_text
from petbot.types import COMMANDS


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

    @contextlib.asynccontextmanager
    async def typing(self) -> AsyncIterator[None]:
        yield


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


def test_without_mention_strips_only_this_bot() -> None:
    # The bot's own mention (both forms) goes; other users' mentions stay.
    assert _without_mention("<@1> hi <@2>", 1) == " hi <@2>"
    assert _without_mention("<@!1> yo", 1) == " yo"


class _RaisingSkills:
    """A Skills client whose every call fails — stands in for an unreachable worker."""

    async def _boom(self, *_: object) -> SkillResult:
        raise RuntimeError("worker unreachable")

    math = derpi = e621 = music = chat = _boom


async def test_chat_maps_transport_error_to_friendly_failure() -> None:
    bot = PetBot(EdgeSettings(discord_token="x", worker=HttpWorker(url="http://worker/dispatch")))
    bot.skills = _RaisingSkills()
    result = await bot._chat("hello", FakeMessage(FakeChannel()))  # type: ignore[arg-type]
    assert result.is_error  # the transport failure became a friendly result, not a crash


# --- slash commands ----------------------------------------------------------


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
    """Captures defer + followups for a slash command, without a gateway."""

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


async def test_respond_interaction_sends_card_as_followup() -> None:
    interaction = FakeInteraction()
    result = SkillResult.message("here", embed=EmbedSpec(title="c", image_url="http://i/x"))
    await respond_interaction(interaction, result)  # type: ignore[arg-type]
    assert interaction.followup.sent[0]["content"] == "here"
    assert interaction.followup.sent[0]["embed"] is not None


class _StubSkills:
    """Records each slash dispatch and returns a canned success."""

    def __init__(self) -> None:
        self.called: list[str] = []
        self.args: list[object] = []

    def _record(self, name: str):  # type: ignore[no-untyped-def]
        async def call(args: object, ctx: object) -> SkillResult:
            self.called.append(name)
            self.args.append(args)
            return SkillResult.message(f"{name} ok")

        return call

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return self._record(name)


async def test_with_defer_acks_before_delegating() -> None:
    # The 3-second rule lives in one wrapper: defer must happen before the handler.
    seen: dict[str, object] = {}

    async def handle(interaction: FakeInteraction, **values: object) -> None:
        seen["deferred_first"] = interaction.response.deferred
        seen["values"] = values

    await _with_defer(handle)(FakeInteraction(), expression="6*7")
    assert seen["deferred_first"] is True
    assert seen["values"] == {"expression": "6*7"}


async def test_slash_command_dispatches_and_followups() -> None:
    # A built command rides the shared pipeline: defer, dispatch the validated args
    # to its skill, send the result as a followup.
    skills = _StubSkills()
    math = next(c for c in build_commands(skills) if c.name == "math")
    interaction = FakeInteraction()
    await math.callback(interaction, expression="6*7")  # type: ignore[arg-type, call-arg]
    assert interaction.response.deferred is True
    assert skills.called == ["math"]
    assert skills.args[0].expression == "6*7"  # type: ignore[attr-defined]
    assert interaction.followup.sent[0]["content"] == "math ok"


async def test_slash_command_maps_failure_to_friendly_followup() -> None:
    e621 = next(c for c in build_commands(_RaisingSkills()) if c.name == "e621")
    interaction = FakeInteraction()
    await e621.callback(interaction, tags="fox")  # type: ignore[arg-type, call-arg]
    assert interaction.response.deferred is True
    # the dispatch failure became a friendly followup, not a crash
    assert interaction.followup.sent[0]["content"] == WORKER_UNREACHABLE


def test_slash_command_options_are_generated_from_args_model() -> None:
    # The edge hand-lists no options: each command's parameters are read straight off
    # the skill's args_model — required/optional preserved, help from the Field.
    spec = next(s for s in COMMANDS if s.name == "e621")

    async def _noop(interaction: object, **values: object) -> None: ...

    command = _as_app_command(spec, _noop)
    assert command.name == "e621"
    params = command._params
    assert set(params) == set(spec.args_model.model_fields)
    assert params["tags"].required is True  # BooruArgs.tags is required
    assert params["sort"].required is False  # BooruArgs.sort is optional
    assert str(params["min_score"].description) == "Minimum score floor."
