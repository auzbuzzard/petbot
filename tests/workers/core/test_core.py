"""The core worker hosts math + booru + chat, with chat wired to its siblings."""

from __future__ import annotations

from petbot.domain import Platform, SkillContext, SkillResult, User
from petbot.workers.core import build_worker
from petbot.workers.core.handler import handler


def test_build_worker_hosts_all_core_skills() -> None:
    names = build_worker().skill_names
    assert {"math", "derpi", "e621", "chat"} <= names
    assert "music" not in names  # music is its own worker


def test_handler_survives_repeated_warm_invocations() -> None:
    # Regression for the persistent-loop fix: a second warm call must not hit a
    # closed event loop. Math needs no network, so it exercises the loop reuse.
    ctx = SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="t"),
        conversation_id="c",
    )
    event = {
        "skill": "math",
        "args": {"expression": "6 * 7"},
        "context": ctx.model_dump(mode="json"),
    }
    for _ in range(2):
        response = handler(event)
        assert response["statusCode"] == 200
        result = SkillResult.model_validate_json(response["body"])
        assert result.text is not None and "42" in result.text
