"""The kernel models are frozen, self-serialising, and reject unknown fields."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from petbot.domain import (
    EmbedSpec,
    Platform,
    SkillCall,
    SkillContext,
    SkillResult,
    User,
)
from petbot.types import MathArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def test_result_helpers() -> None:
    ok = SkillResult.message("hi", embed=EmbedSpec(title="t"))
    assert not ok.is_error
    assert ok.text == "hi"
    assert SkillResult.failure("nope").is_error


def test_result_round_trips() -> None:
    result = SkillResult.message("hi", embed=EmbedSpec(title="t", color=0xFF0000))
    assert SkillResult.model_validate_json(result.model_dump_json()) == result


def test_skill_call_holds_typed_args_in_memory() -> None:
    # SkillCall is an in-memory envelope: args is a live model, not pre-serialised.
    args = MathArgs(expression="6 * 7")
    call = SkillCall(skill="math", args=args, context=_ctx())
    assert call.args is args
    assert call.context.user.display_name == "tester"


def test_models_are_frozen() -> None:
    with pytest.raises(ValidationError):
        _ctx().conversation_id = "other"  # type: ignore[misc]


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillResult.model_validate({"text": "hi", "bogus": 1})
