"""The math skill behaves identically to its in-tree predecessor, and is
discoverable as a ``petbot.skills`` entry point."""

from __future__ import annotations

from importlib.metadata import entry_points

from petbot_domain import Platform, SkillContext, User
from petbot_skill_math import MathSkill


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


async def test_evaluates_expression() -> None:
    result = await MathSkill().run({"expression": "2 * 21"}, _ctx())
    assert not result.is_error
    assert result.text is not None
    assert "42" in result.text


async def test_supports_functions() -> None:
    result = await MathSkill().run({"expression": "sqrt(144)"}, _ctx())
    assert result.text is not None
    assert "12" in result.text


async def test_invalid_expression_is_friendly_output() -> None:
    result = await MathSkill().run({"expression": "2 +"}, _ctx())
    assert not result.is_error
    assert result.text is not None
    assert ">>>" in result.text


def test_metadata() -> None:
    skill = MathSkill()
    assert skill.name == "math"
    assert "expression" in skill.input_schema["properties"]
    assert skill.requires == frozenset()


def test_registered_as_entry_point() -> None:
    math_eps = [ep for ep in entry_points(group="petbot.skills") if ep.name == "math"]
    assert math_eps, "math skill is not registered under the petbot.skills group"
    assert math_eps[0].load() is MathSkill
