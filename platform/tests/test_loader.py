"""The loader discovers installed ``petbot.skills`` plugins; a worker then runs
them straight off the registry."""

from __future__ import annotations

from petbot_domain import Platform, SkillContext, User
from petbot_platform import build_registry


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def test_build_registry_discovers_installed_math_plugin() -> None:
    registry = build_registry()
    assert "math" in {skill.name for skill in registry}


async def test_a_discovered_skill_runs() -> None:
    # The worker's actual path: discover -> get by name -> run. No edge, no
    # dispatch indirection — that hop (edge -> worker) is remote and lands later.
    registry = build_registry()
    result = await registry.get("math").run({"expression": "6 * 7"}, _ctx())
    assert result.text is not None
    assert "42" in result.text
