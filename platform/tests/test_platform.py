"""Worker dispatch, the typed Skills clients, and the HTTP transport round-trip."""

from __future__ import annotations

import httpx
import pytest

from petbot.domain import (
    Platform,
    Skill,
    SkillCall,
    SkillContext,
    SkillResult,
    User,
)
from petbot.platform import HttpTransport, LocalSkills, RemoteSkills, Worker
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
    return SkillCall(
        skill=skill, args_json=MathArgs(expression=expression).model_dump_json(), context=_ctx()
    )


async def test_handle_validates_args_and_runs() -> None:
    worker = Worker([_EchoSkill()])
    result = await worker.handle(_call("math", "6 * 7"))
    assert result.text == "got 6 * 7"


async def test_serve_is_bytes_in_json_out() -> None:
    worker = Worker([_EchoSkill()])
    out = await worker.serve(_call("math", "1 + 1").model_dump_json())
    assert SkillResult.model_validate_json(out).text == "got 1 + 1"


async def test_unknown_skill_is_expected_failure() -> None:
    worker = Worker([_EchoSkill()])
    assert (await worker.handle(_call("nope", "1"))).is_error


async def test_skill_exception_becomes_failure() -> None:
    worker = Worker([_BoomSkill()])
    assert (await worker.handle(_call("boom", "1"))).is_error


async def test_run_skill_runs_in_process_without_json() -> None:
    worker = Worker([_EchoSkill()])
    result = await worker.run_skill("math", MathArgs(expression="9"), _ctx())
    assert result.text == "got 9"


def test_duplicate_skill_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        Worker([_EchoSkill(), _EchoSkill()])


async def test_local_skills_satisfies_the_protocol_and_dispatches() -> None:
    worker = Worker([_EchoSkill()])
    skills: Skills = LocalSkills(worker)  # static: must satisfy the Skills protocol
    result = await skills.math(MathArgs(expression="42"), _ctx())
    assert result.text == "got 42"


async def test_remote_skills_round_trips_over_http_transport() -> None:
    worker = Worker([_EchoSkill()])

    async def _handler(request: httpx.Request) -> httpx.Response:
        out = await worker.serve(request.content)
        return httpx.Response(200, content=out)

    transport = httpx.MockTransport(_handler)
    async with httpx.AsyncClient(transport=transport, base_url="http://worker") as client:
        skills: Skills = RemoteSkills(HttpTransport("http://worker/dispatch", client))
        result = await skills.math(MathArgs(expression="6 * 7"), _ctx())
    assert result.text == "got 6 * 7"
