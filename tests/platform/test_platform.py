"""The tool registry, the serve boundary, the ProcessClient, and the HTTP transport."""

from __future__ import annotations

import json

import httpx
import pytest

from petbot.domain import (
    CommandInput,
    InvalidInput,
    Platform,
    Process,
    Skill,
    SkillContext,
    SkillError,
    SkillResult,
    User,
)
from petbot.platform import HttpTransport, ProcessClient, ToolRegistry, serve
from petbot.types import MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class _EchoSkill(Skill[MathArgs]):
    name = "math"
    description = "echo"
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        return SkillResult.message(f"got {args.expression}")


# --- ToolRegistry -------------------------------------------------------------


async def test_registry_dispatch_validates_and_runs() -> None:
    registry = ToolRegistry([_EchoSkill()])
    result = await registry.dispatch("math", {"expression": "6 * 7"}, _ctx())
    assert result.text == "got 6 * 7"


async def test_registry_unknown_tool_raises_skill_error() -> None:
    registry = ToolRegistry([_EchoSkill()])
    with pytest.raises(SkillError):
        await registry.dispatch("nope", {"expression": "1"}, _ctx())


async def test_registry_bad_args_raise_invalid_input() -> None:
    registry = ToolRegistry([_EchoSkill()])
    with pytest.raises(InvalidInput):
        await registry.dispatch("math", {"not_expression": "x"}, _ctx())


def test_duplicate_skill_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([_EchoSkill(), _EchoSkill()])


# --- serve + transport --------------------------------------------------------


class _EchoProcess(Process):
    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        assert isinstance(inp, CommandInput)
        return SkillResult.message(f"ran {inp.name}")


class _BoomProcess(Process):
    async def respond(self, inp: object, ctx: SkillContext) -> SkillResult:
        raise RuntimeError("kaboom")


def _body(inp: CommandInput) -> str:
    return json.dumps(
        {"input": inp.model_dump(mode="json"), "context": _ctx().model_dump(mode="json")}
    )


async def test_serve_decodes_runs_and_encodes() -> None:
    out = await serve(_EchoProcess(), _body(CommandInput(name="math", values={"expression": "1"})))
    assert SkillResult.model_validate_json(out).text == "ran math"


async def test_serve_maps_malformed_payload_to_result() -> None:
    # Missing fields and outright non-JSON both become a result — never an escaping error.
    assert SkillResult.model_validate_json(await serve(_EchoProcess(), '{"input": {}}')).text
    assert SkillResult.model_validate_json(await serve(_EchoProcess(), "not json")).text


async def test_serve_catches_unexpected_exception() -> None:
    out = await serve(_BoomProcess(), _body(CommandInput(name="math", values={})))
    assert SkillResult.model_validate_json(out).text  # a generic crash result, not a raise


async def test_process_client_http_round_trip() -> None:
    process = _EchoProcess()

    async def _handler(request: httpx.Request) -> httpx.Response:
        out = await serve(process, request.content)
        return httpx.Response(200, content=out)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://svc") as client:
        client_process: Process = ProcessClient(HttpTransport("http://svc/dispatch", client))
        result = await client_process.respond(
            CommandInput(name="math", values={"expression": "6 * 7"}), _ctx()
        )
    assert result.text == "ran math"
