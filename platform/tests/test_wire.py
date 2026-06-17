"""The edge<->worker wire round-trips requests and results, dropping live ports."""

from __future__ import annotations

from petbot_domain import (
    DispatchRequest,
    EmbedSpec,
    Platform,
    SkillContext,
    SkillResult,
    User,
)
from petbot_platform import (
    Worker,
    dump_request,
    dump_result,
    load_request,
    load_result,
)


def _request() -> DispatchRequest:
    ctx = SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="42", display_name="tester"),
        conversation_id="discord:7",
        allows_explicit=True,
        max_text_length=2000,
    )
    return DispatchRequest(skill="math", args={"expression": "6 * 7"}, context=ctx)


def test_request_round_trips() -> None:
    original = _request()
    back = load_request(dump_request(original))
    assert back.skill == "math"
    assert back.args == {"expression": "6 * 7"}
    assert back.context.user.id == "42"
    assert back.context.allows_explicit is True


def test_result_round_trips_with_embed_and_files() -> None:
    original = SkillResult.message(
        "here you go",
        embed=EmbedSpec(title="t", image_url="https://x/y.png", color=0xABCDEF),
        files=("a.png", "b.png"),
    )
    back = load_result(dump_result(original))
    assert back == original


def test_error_result_round_trips() -> None:
    back = load_result(dump_result(SkillResult.failure("nope")))
    assert back.is_error
    assert back.error == "nope"


async def test_full_edge_to_worker_path() -> None:
    # Serialise (edge) -> deserialise + run (worker) -> serialise -> deserialise (edge).
    wire = dump_request(_request())
    result = await Worker.from_installed_skills().handle(load_request(wire))
    back = load_result(dump_result(result))
    assert back.text is not None
    assert "42" in back.text
