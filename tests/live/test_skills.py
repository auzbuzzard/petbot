"""Every skill, through the deployed core's slash path.

An expected failure (an unreachable upstream, an empty search) arrives as voiced text without
the expected facts, so it fails here too.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from petbot.domain import CommandInput, SkillContext
from petbot.frontends.discord.render import SERVICE_UNREACHABLE
from petbot.platform import ProcessClient

TEXT_CASES: list[tuple[str, dict[str, Any], list[str]]] = [
    ("math", {"expression": "6 * 7"}, ["42"]),
    ("leetcode", {"mode": "daily"}, ["LeetCode's daily problem for", "leetcode.com/problems/"]),
    ("leetcode", {"mode": "random", "difficulty": "easy"}, ["(Easy", "leetcode.com/problems/"]),
    ("weather", {"location": "Paris, France"}, ["Paris", "°C"]),
    ("web_search", {"query": "Python programming language"}, ["http"]),
    ("web_fetch", {"url": "https://example.com/"}, ["Example Domain"]),
]

CARD_CASES: list[tuple[str, dict[str, Any]]] = [
    ("derpi", {"tags": "pony"}),
    ("e621", {"tags": "fox"}),
]


def _id(tool: str, values: dict[str, Any]) -> str:
    return f"{tool}:" + ",".join(f"{k}={v}" for k, v in values.items())


@pytest.mark.parametrize(
    ("tool", "values", "expected"), TEXT_CASES, ids=[_id(t, v) for t, v, _ in TEXT_CASES]
)
async def test_a_skill_answers_from_the_deployed_core(
    core: ProcessClient,
    ctx: SkillContext,
    record: Callable[[str, str], None],
    tool: str,
    values: dict[str, Any],
    expected: list[str],
) -> None:
    result = await core.respond(CommandInput(name=tool, values=values), ctx)
    text = result.text or ""
    record(f"/{_id(tool, values)}", text)
    assert text != SERVICE_UNREACHABLE
    missing = [fact for fact in expected if fact not in text]
    assert not missing, f"/{tool} answered without {missing}: {text!r}"


@pytest.mark.parametrize(("tool", "values"), CARD_CASES, ids=[_id(t, v) for t, v in CARD_CASES])
async def test_an_image_search_returns_a_card(
    core: ProcessClient,
    ctx: SkillContext,
    record: Callable[[str, str], None],
    tool: str,
    values: dict[str, Any],
) -> None:
    result = await core.respond(CommandInput(name=tool, values=values), ctx)
    record(f"/{_id(tool, values)}", f"{result.text or ''}\n[card: {result.embed}]")
    assert result.embed is not None and result.embed.image_url, f"/{tool}: {result.text!r}"
