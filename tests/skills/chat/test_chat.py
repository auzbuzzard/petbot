"""The chat skill drives the agent, calls sibling skills as tools, and folds in
any rich card — all without a live LLM (``TestModel``) or live skills (a fake)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_ai.models.test import TestModel

from petbot.domain import EmbedSpec, Platform, SkillContext, SkillResult, User
from petbot.skills.chat import ChatSkill
from petbot.skills.chat.model import build_model
from petbot.skills.chat.settings import ChatSettings, OpenAICompatibleModel, OpenRouterModel
from petbot.types import BooruArgs, ChatArgs, MathArgs, MusicArgs


def test_llm_config_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    # The provider config is required — a missing CHAT_LLM__* fails at construction.
    monkeypatch.delenv("CHAT_LLM__KIND", raising=False)
    monkeypatch.delenv("CHAT_LLM__MODEL", raising=False)
    with pytest.raises(ValidationError):
        ChatSettings(_env_file=None)


def test_openrouter_variant_requires_api_key() -> None:
    # The OpenRouter variant has api_key as a required field — no conditional None.
    with pytest.raises(ValidationError):
        OpenRouterModel(model="x")  # type: ignore[call-arg]  # missing api_key is the point


def test_openai_compatible_variant_requires_base_url_and_key() -> None:
    # base_url + api_key are required fields of this variant (no conditional None).
    with pytest.raises(ValidationError):
        OpenAICompatibleModel(model="x")  # type: ignore[call-arg]


def test_openai_compatible_builds_an_openai_model() -> None:
    # The Bedrock-mantle / Ollama path: build_model wires an OpenAI-compatible
    # client to the given base URL. Construction is offline (no network).
    from pydantic_ai.models.openai import OpenAIChatModel

    settings = ChatSettings(
        llm=OpenAICompatibleModel(
            model="google.gemma-4-26b-a4b",
            base_url="https://bedrock-mantle.us-east-1.api.aws/openai/v1",
            api_key="test-key",
        ),
        _env_file=None,
    )
    assert isinstance(build_model(settings), OpenAIChatModel)


class FakeSkills:
    """Records the sibling calls the agent's tools make; returns canned results."""

    def __init__(self, results: dict[str, SkillResult]) -> None:
        self._results = results
        self.called: list[str] = []

    async def math(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        self.called.append("math")
        return self._results["math"]

    async def derpi(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        self.called.append("derpi")
        return self._results["derpi"]

    async def e621(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        self.called.append("e621")
        return self._results["e621"]

    async def music(self, args: MusicArgs, ctx: SkillContext) -> SkillResult:  # pragma: no cover
        self.called.append("music")
        return self._results["music"]

    async def chat(self, args: ChatArgs, ctx: SkillContext) -> SkillResult:  # pragma: no cover
        self.called.append("chat")
        return self._results["chat"]


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


async def test_agent_calls_math_tool_and_returns_text() -> None:
    fake = FakeSkills({"math": SkillResult.message("```\n42\n```")})
    skill = ChatSkill(fake, model=TestModel(call_tools=["math"]))
    result = await skill.run(ChatArgs(message="what is 6 * 7?"), _ctx())
    assert "math" in fake.called
    assert not result.is_error
    assert result.text  # the model produced a reply


async def test_booru_tool_card_is_surfaced_on_the_reply() -> None:
    image = SkillResult.message(
        "here you go!", embed=EmbedSpec(title="results", image_url="https://img/x.png")
    )
    fake = FakeSkills({"derpi": image})
    skill = ChatSkill(fake, model=TestModel(call_tools=["derpi"]))
    result = await skill.run(ChatArgs(message="show me a pony"), _ctx())
    assert "derpi" in fake.called
    # The rich card a tool produced rides back on the final reply.
    assert result.embed is not None
    assert result.embed.image_url == "https://img/x.png"


async def test_skill_error_does_not_crash_the_agent() -> None:
    fake = FakeSkills({"e621": SkillResult.failure("the booru is down")})
    skill = ChatSkill(fake, model=TestModel(call_tools=["e621"]))
    result = await skill.run(ChatArgs(message="find a fox"), _ctx())
    assert "e621" in fake.called
    assert not result.is_error  # the failure is reported to the model, not raised
