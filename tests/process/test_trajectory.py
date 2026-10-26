from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from petbot.domain import (
    CommandInput,
    Platform,
    Skill,
    SkillContext,
    SkillResult,
    TextInput,
    ToolCall,
    UpstreamUnavailable,
    User,
)
from petbot.platform import ToolRegistry, serve
from petbot.process import ChatProcess, CommandProcess, PassthroughStyle, RouterProcess
from petbot.services import core as core_module
from petbot.services.core import CoreSettings, build_process
from petbot.types import LeetCodeArgs, MathArgs, WeatherArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class _Skill(Skill[BaseModel]):
    def __init__(self, name: str, args_model: type[BaseModel], text: str) -> None:
        self.name = name
        self.description = name
        self.args_model = args_model
        self._text = text

    async def run(self, args: BaseModel, ctx: SkillContext) -> SkillResult:
        return SkillResult.message(self._text)


class _Down(Skill[BaseModel]):
    name = "weather"
    description = "weather"
    args_model = WeatherArgs

    async def run(self, args: BaseModel, ctx: SkillContext) -> SkillResult:
        raise UpstreamUnavailable("the forecast service is down")


def _scripted(*calls: tuple[str, dict[str, Any]]) -> FunctionModel:
    """A model that makes ``calls`` one per step, then answers."""
    steps: Iterator[tuple[str, dict[str, Any]]] = iter(calls)

    def fn(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        step = next(steps, None)
        if step is None:
            return ModelResponse(parts=[TextPart(content="here you go")])
        tool, args = step
        return ModelResponse(parts=[ToolCallPart(tool_name=tool, args=args)])

    return FunctionModel(fn)


def _leetcode() -> ToolRegistry:
    return ToolRegistry([_Skill("leetcode", LeetCodeArgs, "1. Two Sum (Easy)")])


async def test_chat_reports_no_trajectory_by_default() -> None:
    chat = ChatProcess(_leetcode(), model=_scripted(("leetcode", {"mode": "random"})))
    result = await chat.respond(TextInput(text="a random leetcode problem"), _ctx())
    assert result.trajectory is None
    assert "trajectory" not in json.loads(result.model_dump_json())


async def test_chat_reports_each_tool_call_with_its_arguments_and_output() -> None:
    chat = ChatProcess(
        _leetcode(), model=_scripted(("leetcode", {"mode": "random"})), report_trajectory=True
    )
    result = await chat.respond(TextInput(text="a random leetcode problem"), _ctx())
    assert result.text == "here you go"
    assert result.trajectory == (
        ToolCall(
            tool="leetcode", args={"mode": "random"}, outcome="returned", output="1. Two Sum (Easy)"
        ),
    )


async def test_chat_trajectory_shows_a_call_missing_a_required_argument() -> None:
    chat = ChatProcess(_leetcode(), model=_scripted(("leetcode", {})), report_trajectory=True)
    result = await chat.respond(TextInput(text="a random leetcode problem"), _ctx())
    assert result.trajectory is not None
    (call,) = result.trajectory
    assert call.tool == "leetcode" and call.args == {}
    assert call.output is not None and "weren't valid" in call.output


async def test_chat_trajectory_carries_a_skill_error_as_the_tool_output() -> None:
    chat = ChatProcess(
        ToolRegistry([_Down()]),
        model=_scripted(("weather", {"location": "Paris"})),
        report_trajectory=True,
    )
    result = await chat.respond(TextInput(text="weather in Paris?"), _ctx())
    assert result.trajectory is not None
    (call,) = result.trajectory
    assert call.outcome == "returned"
    assert call.args == {"location": "Paris"}
    assert call.output is not None and "the forecast service is down" in call.output


async def test_chat_trajectory_marks_a_call_the_agent_rejected() -> None:
    chat = ChatProcess(
        _leetcode(),
        model=_scripted(("no_such_tool", {"x": 1}), ("leetcode", {"mode": "daily"})),
        report_trajectory=True,
    )
    result = await chat.respond(TextInput(text="today's leetcode"), _ctx())
    assert result.trajectory is not None
    assert [(c.tool, c.outcome) for c in result.trajectory] == [
        ("no_such_tool", "rejected"),
        ("leetcode", "returned"),
    ]


async def test_chat_trajectory_is_empty_when_no_tool_is_called() -> None:
    chat = ChatProcess(_leetcode(), model=_scripted(), report_trajectory=True)
    result = await chat.respond(TextInput(text="hi!"), _ctx())
    assert result.trajectory == ()


async def test_command_reports_no_trajectory_by_default() -> None:
    registry = ToolRegistry([_Skill("math", MathArgs, "42")])
    process = CommandProcess(registry, PassthroughStyle())
    result = await process.respond(CommandInput(name="math", values={"expression": "6*7"}), _ctx())
    assert result.trajectory is None


async def test_command_reports_its_one_call_with_the_unvoiced_output() -> None:
    registry = ToolRegistry([_Skill("math", MathArgs, "42"), _Down()])
    process = CommandProcess(registry, PassthroughStyle(), report_trajectory=True)
    result = await process.respond(CommandInput(name="math", values={"expression": "6*7"}), _ctx())
    assert result.trajectory == (
        ToolCall(tool="math", args={"expression": "6*7"}, outcome="returned", output="42"),
    )
    failed = await process.respond(CommandInput(name="weather", values={"location": "x"}), _ctx())
    assert failed.trajectory is not None
    assert failed.trajectory[0].output == "the forecast service is down"


async def test_the_trajectory_travels_in_the_dispatch_result() -> None:
    registry = ToolRegistry([_Skill("math", MathArgs, "42")])
    process = RouterProcess(
        chat=None, command=CommandProcess(registry, PassthroughStyle(), report_trajectory=True)
    )
    body = json.dumps(
        {
            "input": CommandInput(name="math", values={"expression": "6*7"}).model_dump(
                mode="json"
            ),
            "context": _ctx().model_dump(mode="json"),
        }
    )
    result = SkillResult.model_validate_json(await serve(process, body))
    assert result.trajectory == (
        ToolCall(tool="math", args={"expression": "6*7"}, outcome="returned", output="42"),
    )


def test_core_reports_no_trajectory_unless_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CORE_REPORT_TRAJECTORY", raising=False)
    assert CoreSettings(_env_file=None).report_trajectory is False
    monkeypatch.setenv("CORE_REPORT_TRAJECTORY", "true")
    assert CoreSettings(_env_file=None).report_trajectory is True


@pytest.mark.parametrize("configured", [False, True])
async def test_the_core_service_reports_a_trajectory_only_when_configured(
    monkeypatch: pytest.MonkeyPatch, configured: bool
) -> None:
    if configured:
        monkeypatch.setenv("CORE_REPORT_TRAJECTORY", "true")
    else:
        monkeypatch.delenv("CORE_REPORT_TRAJECTORY", raising=False)
    # The slash path's voice is a model call; this checks the wiring, not the voice.
    monkeypatch.setattr(core_module, "Stylist", lambda settings: PassthroughStyle())
    body = json.dumps(
        {
            "input": CommandInput(name="math", values={"expression": "6 * 7"}).model_dump(
                mode="json"
            ),
            "context": _ctx().model_dump(mode="json"),
        }
    )
    wire = json.loads(await serve(build_process(), body))
    if configured:
        assert wire["trajectory"][0]["tool"] == "math"
        assert "42" in wire["trajectory"][0]["output"]
    else:
        assert "trajectory" not in wire
