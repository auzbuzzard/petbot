"""InProcessDispatch closes the loop: discover -> registry -> run -> result."""

from __future__ import annotations

from petbot_domain import DispatchPort, DispatchRequest, Platform, SkillContext, User
from petbot_platform import InProcessDispatch, build_registry


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def test_satisfies_dispatch_port() -> None:
    assert isinstance(InProcessDispatch(build_registry()), DispatchPort)


async def test_dispatch_runs_a_real_plugin() -> None:
    dispatch = InProcessDispatch(build_registry())
    out = await dispatch.dispatch(
        DispatchRequest(skill="math", args={"expression": "6 * 7"}, context=_ctx())
    )
    assert out.text is not None
    assert "42" in out.text


async def test_dispatch_unknown_skill_is_expected_failure() -> None:
    dispatch = InProcessDispatch(build_registry())
    out = await dispatch.dispatch(DispatchRequest(skill="nope", args={}, context=_ctx()))
    assert out.is_error
