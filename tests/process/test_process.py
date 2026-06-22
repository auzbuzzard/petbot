"""The process core: the chat agent, the command process, the router, and the stylist —
all without a live LLM (``TestModel``) or live skills (fakes in a real ToolRegistry)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from petbot.domain import (
    CommandInput,
    EmbedSpec,
    Platform,
    Process,
    Role,
    Skill,
    SkillContext,
    SkillResult,
    StylePort,
    TextInput,
    Turn,
    UpstreamUnavailable,
    User,
)
from petbot.platform import ToolRegistry
from petbot.process import ChatProcess, CommandProcess, PassthroughStyle, RouterProcess, Stylist
from petbot.process.context import (
    SlidingWindow,
    Summarizer,
    build_compactor,
    is_context_overflow,
)
from petbot.process.history import drop_leading_assistant, to_model_messages
from petbot.process.model import build_model, build_model_from_config
from petbot.process.settings import (
    BedrockModel,
    ChatSettings,
    OpenAICompatibleModel,
    OpenRouterModel,
    SlidingWindowContext,
    SummarizeContext,
)
from petbot.types import BooruArgs, MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class _FakeSkill(Skill[BaseModel]):
    """A tool that records its calls and returns a canned result."""

    def __init__(self, name: str, args_model: type[BaseModel], result: SkillResult) -> None:
        self.name = name
        self.description = name
        self.args_model = args_model
        self._result = result
        self.calls = 0

    async def run(self, args: BaseModel, ctx: SkillContext) -> SkillResult:
        self.calls += 1
        return self._result


class _RaisingSkill(Skill[BaseModel]):
    """A tool whose expected failure is raised, not returned."""

    def __init__(self, name: str, args_model: type[BaseModel]) -> None:
        self.name = name
        self.description = name
        self.args_model = args_model

    async def run(self, args: BaseModel, ctx: SkillContext) -> SkillResult:
        raise UpstreamUnavailable("the booru is down")


def _registry(*skills: Skill[Any]) -> ToolRegistry:
    return ToolRegistry(skills)


# --- settings + model builder (provider-agnostic, offline) --------------------


def test_llm_config_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAT_LLM__KIND", raising=False)
    monkeypatch.delenv("CHAT_LLM__MODEL", raising=False)
    with pytest.raises(ValidationError):
        ChatSettings(_env_file=None)


def test_openrouter_variant_requires_api_key() -> None:
    with pytest.raises(ValidationError):
        OpenRouterModel(model="x")  # type: ignore[call-arg]


def test_openai_compatible_variant_requires_base_url_and_key() -> None:
    with pytest.raises(ValidationError):
        OpenAICompatibleModel(model="x")  # type: ignore[call-arg]


def _settings(**kw: object) -> ChatSettings:
    return ChatSettings(
        llm=OpenAICompatibleModel(model="m", base_url="https://x/v1", api_key="k"),
        _env_file=None,
        **kw,  # type: ignore[arg-type]
    )


def test_openai_compatible_builds_an_openai_model() -> None:
    from pydantic_ai.models.openai import OpenAIChatModel

    assert isinstance(build_model(_settings()), OpenAIChatModel)


def test_system_prompt_composes_persona_and_agent_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAT_SYSTEM_PROMPT", raising=False)
    settings = _settings()
    assert "PetBot" in settings.system_prompt
    assert "age-gated" in settings.system_prompt


def test_system_prompt_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHAT_SYSTEM_PROMPT", "Be terse.")
    assert _settings().system_prompt == "Be terse."


def test_stylizer_prompt_shares_the_persona(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHAT_STYLIZER_PROMPT", raising=False)
    stylizer_prompt = _settings().stylizer_prompt
    assert "PetBot" in stylizer_prompt
    assert "voice" in stylizer_prompt.lower()


def test_stylizer_defaults_to_the_agent_model() -> None:
    settings = _settings()
    assert settings.stylizer is None
    assert settings.stylizer_llm() == settings.llm


def test_stylizer_uses_its_own_tier_when_configured() -> None:
    nova = BedrockModel(model="amazon.nova-micro-v1:0")
    settings = _settings(stylizer=nova)
    assert settings.stylizer_llm() == nova
    assert settings.stylizer_llm() != settings.llm


def test_build_model_from_config_builds_each_role() -> None:
    from pydantic_ai.models.openai import OpenAIChatModel

    cfg = OpenAICompatibleModel(model="m", base_url="https://x/v1", api_key="k")
    assert isinstance(build_model_from_config(cfg), OpenAIChatModel)


# --- the stylist (the persona voice) ------------------------------------------


async def test_stylist_rewrites_result_text_in_character() -> None:
    stylist = Stylist(model=TestModel(custom_output_text="meep~ those tags came up empty"))
    result = await stylist.stylize(SkillResult.message("No results found for those tags."), _ctx())
    assert result.text == "meep~ those tags came up empty"


async def test_stylist_greets_over_a_found_image() -> None:
    stylist = Stylist(model=TestModel(custom_output_text="^v^ here you go~"))
    found = SkillResult.message(embed=EmbedSpec(title="result", image_url="https://img/x.png"))
    result = await stylist.stylize(found, _ctx())
    assert result.text == "^v^ here you go~"
    assert result.embed is not None and result.embed.image_url == "https://img/x.png"


# --- the chat process (the agent + its tools) ---------------------------------


async def test_chat_calls_math_tool_and_returns_text() -> None:
    math = _FakeSkill("math", MathArgs, SkillResult.message("```\n42\n```"))
    chat = ChatProcess(_registry(math), model=TestModel(call_tools=["math"]))
    result = await chat.respond(TextInput(text="what is 6 * 7?"), _ctx())
    assert math.calls == 1
    assert result.text


async def test_chat_surfaces_a_booru_tool_card() -> None:
    card = SkillResult.message(
        "here you go!", embed=EmbedSpec(title="results", image_url="https://img/x.png")
    )
    derpi = _FakeSkill("derpi", BooruArgs, card)
    chat = ChatProcess(_registry(derpi), model=TestModel(call_tools=["derpi"]))
    result = await chat.respond(TextInput(text="show me a pony"), _ctx())
    assert derpi.calls == 1
    assert result.embed is not None and result.embed.image_url == "https://img/x.png"


async def test_chat_tool_error_does_not_crash_the_agent() -> None:
    registry = _registry(_RaisingSkill("e621", BooruArgs))
    chat = ChatProcess(registry, model=TestModel(call_tools=["e621"]))
    result = await chat.respond(TextInput(text="find a fox"), _ctx())
    assert result.text  # the failure is reported to the model, not raised


# --- the command process (dispatch + uniform styling) -------------------------


async def test_command_process_runs_and_styles() -> None:
    registry = _registry(_FakeSkill("math", MathArgs, SkillResult.message("42")))
    process = CommandProcess(registry, PassthroughStyle())
    result = await process.respond(CommandInput(name="math", values={"expression": "6*7"}), _ctx())
    assert result.text == "42"


class _MarkStyle(StylePort):
    """A fake StylePort that wraps the text, so the styling step is observable."""

    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult:
        return result.model_copy(update={"text": f"~{result.text}~"})


async def test_command_process_voices_a_raised_skill_error() -> None:
    # D18: a skill raises; the command process catches it at the output boundary and
    # voices the message through the same StylePort as a success.
    registry = _registry(_RaisingSkill("e621", BooruArgs))
    process = CommandProcess(registry, _MarkStyle())
    result = await process.respond(CommandInput(name="e621", values={"tags": "x"}), _ctx())
    assert result.text == "~the booru is down~"


# --- the router (the one exhaustive match) ------------------------------------


class _Recorder(Process):
    def __init__(self, label: str) -> None:
        self.label = label

    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        return SkillResult.message(self.label)


async def test_router_routes_by_input_type() -> None:
    router = RouterProcess(chat=_Recorder("chat"), command=_Recorder("command"))
    assert (await router.respond(TextInput(text="hi"), _ctx())).text == "chat"
    assert (await router.respond(CommandInput(name="math", values={}), _ctx())).text == "command"


async def test_router_without_chat_rejects_conversational_input() -> None:
    router = RouterProcess(chat=None, command=_Recorder("command"))
    with pytest.raises(TypeError):
        await router.respond(TextInput(text="hi"), _ctx())


# --- history mapping (neutral Turn -> pydantic-ai message_history) -------------


def _texts(messages: list[ModelMessage]) -> list[tuple[str, str]]:
    """``(kind, text)`` for each string part, for compact assertions."""
    out: list[tuple[str, str]] = []
    for message in messages:
        for part in message.parts:
            content = getattr(part, "content", None)
            if isinstance(content, str):
                out.append((message.kind, content))
    return out


def test_to_model_messages_inlines_user_author_not_assistant() -> None:
    # The user turn is prefixed with its author (multi-user attribution); the bot turn
    # isn't — the model owns its own replies.
    msgs = to_model_messages(
        (
            Turn(role=Role.USER, author="Alice", text="show me a pony"),
            Turn(role=Role.ASSISTANT, author="PetBot", text="here you go!"),
        )
    )
    assert _texts(msgs) == [("request", "Alice: show me a pony"), ("response", "here you go!")]


def test_to_model_messages_merges_consecutive_same_role() -> None:
    msgs = to_model_messages(
        (
            Turn(role=Role.USER, author="Alice", text="one"),
            Turn(role=Role.USER, author="Bob", text="two"),
        )
    )
    assert _texts(msgs) == [("request", "Alice: one\nBob: two")]


def test_to_model_messages_drops_empty_turns() -> None:
    msgs = to_model_messages(
        (
            Turn(role=Role.USER, author="Alice", text="real"),
            Turn(role=Role.ASSISTANT, author="PetBot", text="   "),  # empty -> dropped
        )
    )
    assert _texts(msgs) == [("request", "Alice: real")]


def test_to_model_messages_drops_leading_assistant_turns() -> None:
    # History must begin with a user message (providers reject an assistant-first run), so
    # a leading bot turn is dropped.
    msgs = to_model_messages(
        (
            Turn(role=Role.ASSISTANT, author="PetBot", text="earlier reply"),
            Turn(role=Role.USER, author="Alice", text="hi"),
        )
    )
    assert _texts(msgs) == [("request", "Alice: hi")]


def test_to_model_messages_lone_assistant_history_is_empty() -> None:
    # A reply to an image-only bot card with no prior user turn: nothing to prepend.
    msgs = to_model_messages((Turn(role=Role.ASSISTANT, author="PetBot", text="hi"),))
    assert msgs == []


def test_drop_leading_assistant_keeps_from_first_user() -> None:
    # The shared guard the mapper and post-compaction path both apply: a compacted slice
    # that begins with a bot message is trimmed to the first user message.
    messages: list[ModelMessage] = [
        ModelResponse(parts=[TextPart(content="earlier bot reply")]),
        ModelRequest(parts=[UserPromptPart(content="user")]),
        ModelResponse(parts=[TextPart(content="bot")]),
    ]
    assert drop_leading_assistant(messages) == messages[1:]
    assert drop_leading_assistant(messages[2:]) == []  # all-assistant -> nothing


# --- reactive context compaction ----------------------------------------------


def _overflow() -> ModelHTTPError:
    return ModelHTTPError(
        status_code=400,
        model_name="m",
        body={"error": {"message": "maximum context length is 8192 tokens"}},
    )


def test_is_context_overflow_matches_only_length_rejections() -> None:
    server_error = ModelHTTPError(status_code=500, model_name="m", body="boom")
    assert is_context_overflow(_overflow()) is True
    assert is_context_overflow(server_error) is False
    assert is_context_overflow(ValueError("nope")) is False


def test_build_compactor_selects_strategy_from_config() -> None:
    assert isinstance(build_compactor(_settings(context=SlidingWindowContext())), SlidingWindow)
    assert isinstance(build_compactor(_settings(context=SummarizeContext())), Summarizer)


def _history(n: int) -> list[ModelMessage]:
    return [ModelRequest(parts=[UserPromptPart(content=f"m{i}")]) for i in range(n)]


async def test_sliding_window_drops_oldest_half() -> None:
    history = _history(4)
    assert await SlidingWindow().compact(history) == history[2:]


async def test_sliding_window_leaves_a_single_message() -> None:
    history = _history(1)
    assert await SlidingWindow().compact(history) == history


async def test_summarizer_replaces_oldest_half_with_a_summary() -> None:
    summarizer = Summarizer(model=TestModel(custom_output_text="earlier: ponies"))
    history = _history(4)
    compacted = await summarizer.compact(history)
    assert len(compacted) == 3  # one summary note + the recent half (2)
    assert compacted[1:] == history[2:]
    note = compacted[0]
    assert isinstance(note, ModelRequest)
    assert "earlier: ponies" in _texts([note])[0][1]


# --- the chat process retries on a provider length rejection ------------------


async def test_chat_compacts_and_retries_on_context_overflow() -> None:
    calls = {"n": 0}

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _overflow()
        return ModelResponse(parts=[TextPart(content="recovered")])

    chat = ChatProcess(_registry(), model=FunctionModel(fn))
    history = tuple(
        Turn(role=Role.USER if i % 2 == 0 else Role.ASSISTANT, author="x", text=f"t{i}")
        for i in range(6)
    )
    result = await chat.respond(TextInput(text="now", history=history), _ctx())
    assert calls["n"] == 2  # first attempt overflowed; the compacted retry succeeded
    assert result.text == "recovered"


async def test_chat_passes_prior_turns_as_message_history() -> None:
    captured: list[ModelMessage] = []

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        captured.extend(messages)
        return ModelResponse(parts=[TextPart(content="ok")])

    chat = ChatProcess(_registry(), model=FunctionModel(fn))
    history = (
        Turn(role=Role.USER, author="Alice", text="what's a pony?"),
        Turn(role=Role.ASSISTANT, author="PetBot", text="a small horse"),
    )
    await chat.respond(TextInput(text="and a foal?", history=history), _ctx())
    seen = [text for _, text in _texts(captured)]
    assert "Alice: what's a pony?" in seen
    assert "a small horse" in seen
    assert any("and a foal?" in text for text in seen)
