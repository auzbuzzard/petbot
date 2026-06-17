"""Worker dispatch, the typed SkillsClient, and the local/HTTP transports."""

from __future__ import annotations

import httpx
import pytest

from petbot.domain import Platform, Skill, SkillCall, SkillContext, SkillResult, User
from petbot.platform import HttpTransport, LocalTransport, SkillsClient, Worker
from petbot.types import MathArgs, Skills


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


class _BoomSkill(Skill[MathArgs]):
    name = "boom"
    description = "raises"
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        raise RuntimeError("kaboom")


def _call(skill: str, expression: str) -> SkillCall:
    return SkillCall(skill=skill, args=MathArgs(expression=expression), context=_ctx())


async def test_run_uses_typed_args() -> None:
    worker = Worker([_EchoSkill()])
    result = await worker.run(_call("math", "6 * 7"))
    assert result.text == "got 6 * 7"


async def test_serve_decodes_validates_and_encodes() -> None:
    worker = Worker([_EchoSkill()])
    ctx_json = _ctx().model_dump_json()
    wire = f'{{"skill": "math", "args": {{"expression": "1 + 1"}}, "context": {ctx_json}}}'
    out = await worker.serve(wire)
    assert SkillResult.model_validate_json(out).text == "got 1 + 1"


async def test_unknown_skill_is_expected_failure() -> None:
    worker = Worker([_EchoSkill()])
    assert (await worker.run(_call("nope", "1"))).is_error


async def test_skill_exception_becomes_failure() -> None:
    worker = Worker([_BoomSkill()])
    assert (await worker.run(_call("boom", "1"))).is_error


def test_duplicate_skill_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        Worker([_EchoSkill(), _EchoSkill()])


async def test_local_transport_runs_in_process_without_json() -> None:
    worker = Worker([_EchoSkill()])
    skills: Skills = SkillsClient(LocalTransport(worker))  # satisfies the protocol
    result = await skills.math(MathArgs(expression="42"), _ctx())
    assert result.text == "got 42"


async def test_http_transport_round_trip() -> None:
    worker = Worker([_EchoSkill()])

    async def _handler(request: httpx.Request) -> httpx.Response:
        out = await worker.serve(request.content)
        return httpx.Response(200, content=out)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        skills: Skills = SkillsClient(HttpTransport("http://worker/dispatch", client))
        result = await skills.math(MathArgs(expression="6 * 7"), _ctx())
    assert result.text == "got 6 * 7"
