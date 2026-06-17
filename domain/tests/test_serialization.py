"""Domain models self-serialise across the edge<->worker boundary (pydantic).

This is the whole "wire": the models' own ``model_dump_json`` /
``model_validate_json`` — no hand-rolled mapping layer.
"""

from __future__ import annotations

from petbot_domain import (
    DispatchRequest,
    EmbedSpec,
    Platform,
    SkillContext,
    SkillResult,
    User,
)


def _request() -> DispatchRequest:
    return DispatchRequest(
        skill="math",
        args={"expression": "6 * 7"},
        context=SkillContext(
            platform=Platform.DISCORD,
            user=User(platform=Platform.DISCORD, id="42", display_name="tester"),
            conversation_id="discord:7",
            allows_explicit=True,
        ),
    )


def test_request_round_trips() -> None:
    back = DispatchRequest.model_validate_json(_request().model_dump_json())
    assert back == _request()


def test_result_round_trips_with_embed_and_files() -> None:
    original = SkillResult.message(
        "here you go",
        embed=EmbedSpec(title="t", image_url="https://x/y.png", color=0xABCDEF),
        files=("a.png", "b.png"),
    )
    back = SkillResult.model_validate_json(original.model_dump_json())
    assert back == original


def test_failure_round_trips() -> None:
    back = SkillResult.model_validate_json(SkillResult.failure("nope").model_dump_json())
    assert back.is_error
    assert back.error == "nope"
