"""The kernel models are frozen, self-serialising, and reject unknown fields."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from petbot.domain import (
    CommandInput,
    EmbedSpec,
    Input,
    Platform,
    Role,
    SkillContext,
    SkillResult,
    TextInput,
    Turn,
    User,
)


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def test_result_message_carries_text_and_embed() -> None:
    ok = SkillResult.message("hi", embed=EmbedSpec(title="t"))
    assert ok.text == "hi"
    assert ok.embed is not None


def test_result_round_trips() -> None:
    result = SkillResult.message("hi", embed=EmbedSpec(title="t", color=0xFF0000))
    assert SkillResult.model_validate_json(result.model_dump_json()) == result


def test_models_are_frozen() -> None:
    with pytest.raises(ValidationError):
        _ctx().conversation_id = "other"  # type: ignore[misc]


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillResult.model_validate({"text": "hi", "bogus": 1})


def test_text_input_history_round_trips() -> None:
    # History rides on the wire inside the Input sum type: dump to JSON-able data, then
    # re-hydrate the right member by `kind` — tuple + Role enum + nested Turn survive.
    inp = TextInput(
        text="and another?",
        history=(
            Turn(role=Role.USER, author="Alice", text="show me a pony"),
            Turn(role=Role.ASSISTANT, author="PetBot", text="here you go!"),
        ),
    )
    adapter: TypeAdapter[Input] = TypeAdapter(Input)
    assert adapter.validate_python(inp.model_dump(mode="json")) == inp


def test_command_input_has_no_history() -> None:
    # History is sum-type-local: only the conversational variant carries it.
    assert "history" not in CommandInput.model_fields
