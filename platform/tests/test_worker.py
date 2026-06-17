"""The worker runs the dispatched skill, and turns failures into result objects."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from petbot_domain import DispatchRequest, Platform, Skill, SkillContext, SkillResult, User
from petbot_platform import SkillRegistry, Worker, build_registry


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def _request(skill: str, **args: Any) -> DispatchRequest:
    return DispatchRequest(skill=skill, args=args, context=_ctx())


async def test_handle_runs_a_real_plugin() -> None:
    worker = Worker.from_installed_skills()
    result = await worker.handle(_request("math", expression="6 * 7"))
    assert result.text is not None
    assert "42" in result.text


async def test_unknown_skill_is_expected_failure() -> None:
    worker = Worker(build_registry())
    result = await worker.handle(_request("nope"))
    assert result.is_error


async def test_skill_exception_becomes_failure_result() -> None:
    class _Boom(Skill):
        name = "boom"
        description = "raises"
        input_schema: Mapping[str, Any] = {"type": "object"}

        async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
            raise RuntimeError("kaboom")

    worker = Worker(SkillRegistry([_Boom()]))
    result = await worker.handle(_request("boom"))
    assert result.is_error
