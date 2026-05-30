"""Tests for the neutral math skill."""

from __future__ import annotations

from conftest import make_context

from petbot.core.skills.math_skill import MathSkill


async def test_evaluates_expression() -> None:
    result = await MathSkill().run({"expression": "2 * 21"}, make_context())
    assert not result.is_error
    assert result.text is not None
    assert "42" in result.text


async def test_supports_functions() -> None:
    result = await MathSkill().run({"expression": "sqrt(144)"}, make_context())
    assert result.text is not None
    assert "12" in result.text


async def test_invalid_expression_is_friendly_output_not_error() -> None:
    # The legacy behavior: the error is the output, shown in the code block.
    result = await MathSkill().run({"expression": "2 +"}, make_context())
    assert not result.is_error
    assert result.text is not None
    assert ">>>" in result.text


def test_metadata() -> None:
    skill = MathSkill()
    assert skill.name == "math"
    assert "expression" in skill.input_schema["properties"]
    assert skill.requires == frozenset()
