"""The math skill evaluates expressions and reports errors as output."""

from __future__ import annotations

from petbot.domain import Platform, SkillContext, User
from petbot.skills.math import MathSkill
from petbot.types import MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


async def test_evaluates_expression() -> None:
    result = await MathSkill().run(MathArgs(expression="6 * 7"), _ctx())
    assert not result.is_error
    assert result.text is not None and "42" in result.text


async def test_bad_expression_is_output_not_failure() -> None:
    result = await MathSkill().run(MathArgs(expression="this is not math"), _ctx())
    # The legacy contract: the error is shown as output, not an expected failure.
    assert not result.is_error
    assert result.text is not None
