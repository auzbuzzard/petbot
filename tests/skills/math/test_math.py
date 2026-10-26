from __future__ import annotations

import pytest

from petbot.domain import Platform, SkillContext, User
from petbot.skills.math import MathSkill
from petbot.skills.math.skill import evaluate
from petbot.types import MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


async def test_evaluates_expression() -> None:
    result = await MathSkill().run(MathArgs(expression="6 * 7"), _ctx())
    assert result.text is not None and "42" in result.text


async def test_bad_expression_is_output_not_raised() -> None:
    result = await MathSkill().run(MathArgs(expression="this is not math"), _ctx())
    assert result.text is not None


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        ("6 * 7", "42"),
        ("7 / 2", "3.5"),
        ("7 // 2", "3"),
        ("-3 % 5", "2"),
        ("2 ** 10", "1024"),
        ("2 ** -1", "0.5"),
        ("-(1 + 2) * +3", "-9"),
        ("1e3", "1000.0"),
        ("sqrt(144)", "12.0"),
        ("abs(-2)", "2"),
        ("ceil(2.5)", "3.0"),
        ("maximum(1, 2)", "2"),
        ("hypot(3, 4)", "5.0"),
        ("2 ** 63", "9223372036854775808"),
    ],
)
async def test_valid_expressions(expression: str, expected: str) -> None:
    result = await MathSkill().run(MathArgs(expression=expression), _ctx())
    assert result.text == f"```py\n>>>\t{expression}\n<<<\t{expected}\n```"


@pytest.mark.parametrize(
    ("expression", "error"),
    [
        ("x", "unknown name 'x'"),
        ("__import__('os')", "unknown function '__import__'"),
        ("eval('1')", "unknown function 'eval'"),
        ("(1).real", "unsupported expression"),
        ("sqrt.__class__", "unsupported expression"),
        ("[1, 2]", "unsupported expression"),
        ("'a' * 3", "unsupported expression"),
        ("True + 1", "unsupported expression"),
        ("1 < 2", "unsupported expression"),
        ("lambda: 1", "unsupported expression"),
        ("sqrt(1, 2)", "sqrt() takes 1 argument"),
        ("sqrt(x=4)", "sqrt() takes 1 argument"),
        ("9 ** 9 ** 9", "result is too large"),
        ("2 ** 2 ** 2 ** 2 ** 2", "result is too large"),
        ("(2 ** 1000) * (2 ** 1000)", "result is too large"),
        ("1" + " + 1" * 100, "expression is longer than 256 characters"),
    ],
)
async def test_rejected_expressions(expression: str, error: str) -> None:
    result = await MathSkill().run(MathArgs(expression=expression), _ctx())
    assert result.text == f"```py\n>>>\t{expression}\n<<<\t{error}\n```"


def test_power_cap_is_checked_before_computing() -> None:
    with pytest.raises(ValueError, match="too large"):
        evaluate("10 ** 1000000000")
