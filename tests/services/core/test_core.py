"""The core service: the installed-tool registry and the Lambda handler plumbing."""

from __future__ import annotations

import pytest

from petbot.domain import (
    CommandInput,
    Input,
    Platform,
    Process,
    SkillContext,
    SkillResult,
    User,
)
from petbot.platform import ToolRegistry, remaining
from petbot.process import CommandProcess, PassthroughStyle, RouterProcess
from petbot.services.core import handler as handler_module


def test_installed_tools_are_the_stateless_skills() -> None:
    names = ToolRegistry.from_installed_skills().names
    assert {"math", "derpi", "e621"} <= names
    assert "music" not in names  # music is its own service
    assert "chat" not in names  # chat is the process, not a tool


def test_handler_returns_bare_skill_result_across_warm_invocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The handler returns the SkillResult verbatim (no HTTP envelope) so the frontend's
    # LambdaTransport can parse the invoke Payload directly. Also a regression for the
    # persistent-loop fix: a second warm call must not hit a closed event loop. Math runs
    # through a passthrough-styled command process — no LLM, no network.
    process = RouterProcess(
        chat=None,
        command=CommandProcess(ToolRegistry.from_installed_skills(), PassthroughStyle()),
    )
    monkeypatch.setattr(handler_module, "_process", process)

    ctx = SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="t"),
        conversation_id="c",
    )
    event = {
        "input": CommandInput(name="math", values={"expression": "6 * 7"}).model_dump(mode="json"),
        "context": ctx.model_dump(mode="json"),
    }
    for _ in range(2):
        response = handler_module.handler(event)
        assert "statusCode" not in response  # bare result, not an API-Gateway envelope
        result = SkillResult.model_validate(response)
        assert result.text is not None and "42" in result.text


def test_handler_gives_the_turn_the_invocation_time_minus_a_reserve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The turn's budget comes from the Lambda invocation's own clock, less the reserve kept
    # for encoding the result and flushing telemetry.
    seen: list[float | None] = []

    class _Recorder(Process):
        async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
            seen.append(remaining())
            return SkillResult.message("ok")

    class _LambdaContext:
        def get_remaining_time_in_millis(self) -> int:
            return 60_000

    monkeypatch.setattr(handler_module, "_process", _Recorder())
    ctx = SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="t"),
        conversation_id="c",
    )
    event = {
        "input": CommandInput(name="math", values={}).model_dump(mode="json"),
        "context": ctx.model_dump(mode="json"),
    }

    class _AlmostOutOfTime:
        def get_remaining_time_in_millis(self) -> int:
            return 1_000  # less than the reserve

    handler_module.handler(event, _LambdaContext())
    handler_module.handler(event)  # no Lambda context: unbounded
    handler_module.handler(event, _AlmostOutOfTime())
    reserve = handler_module._RESERVE_SECONDS
    assert seen[0] is not None and 60 - reserve - 1 < seen[0] <= 60 - reserve
    assert seen[1] is None
    assert seen[2] == 0.0  # clamped: a zero budget, never a negative one
