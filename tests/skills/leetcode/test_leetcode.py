"""The LeetCode skill against mocked GraphQL responses (no live API calls)."""

from __future__ import annotations

import json
import random
from typing import Any

import httpx
import pytest
import respx

from petbot.domain import EmptyResult, Platform, SkillContext, UpstreamUnavailable, User
from petbot.skills.leetcode.skill import (
    CATEGORY,
    GRAPHQL_URL,
    PAGE_SIZE,
    Daily,
    GraphQLProvider,
    LeetCodeProvider,
    LeetCodeSkill,
    Problem,
)
from petbot.types import LeetCodeArgs, LeetCodeDifficulty


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


def _question(
    number: str, title: str, difficulty: str = "Easy", *, paid: bool = False
) -> dict[str, Any]:
    return {
        "questionFrontendId": number,
        "title": title,
        "titleSlug": title.lower().replace(" ", "-"),
        "difficulty": difficulty,
        "acRate": 58.04,
        "paidOnly": paid,
        "topicTags": [{"name": "Array"}, {"name": "Hash Table"}],
    }


_DAILY: dict[str, Any] = {
    "data": {
        "activeDailyCodingChallengeQuestion": {
            "date": "2026-10-22",
            "question": {
                **_question("3942", "Minimum Operations to Sort a Permutation", "Medium"),
                "acRate": 52.455510529121256,
                "topicTags": [{"name": "Array"}],
            },
        }
    }
}


def _listing(total: int, questions: list[dict[str, Any]]) -> dict[str, Any]:
    return {"data": {"problemsetQuestionList": {"total": total, "questions": questions}}}


class _FixedRng(random.Random):
    """Lands every offset on ``offset`` and picks the first candidate."""

    def __init__(self, offset: int) -> None:
        super().__init__()
        self._offset = offset

    def randrange(self, *args: Any, **kwargs: Any) -> int:
        return self._offset

    def choice(self, seq: Any) -> Any:
        return seq[0]


def _bodies(route: respx.Route) -> list[dict[str, Any]]:
    return [json.loads(call.request.content) for call in route.calls]


@respx.mock
async def test_daily_reports_the_dated_problem_with_its_difficulty_and_link() -> None:
    route = respx.post(GRAPHQL_URL).respond(json=_DAILY)
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(LeetCodeArgs(), _ctx())
    assert _bodies(route)[0]["operationName"] == "questionOfToday"
    assert result.embed is None
    assert result.text == (
        "LeetCode's daily problem for 2026-10-22:\n"
        "#3942 Minimum Operations to Sort a Permutation (Medium, 52.5% acceptance)\n"
        "Topics: Array\n"
        "<https://leetcode.com/problems/minimum-operations-to-sort-a-permutation/>"
    )


@respx.mock
async def test_daily_ignores_a_difficulty() -> None:
    respx.post(GRAPHQL_URL).respond(json=_DAILY)
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs(mode="daily", difficulty="easy"), _ctx()
        )
    assert result.text is not None and "(Medium," in result.text


@respx.mock
async def test_random_counts_then_pages_the_algorithms_set_at_its_difficulty() -> None:
    page = [_question("7", "Reverse Integer", paid=True), _question("9", "Palindrome Number")]
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(810, [_question("1", "Two Sum")])),
            httpx.Response(200, json=_listing(810, page)),
        ]
    )
    async with httpx.AsyncClient() as client:
        skill = LeetCodeSkill([GraphQLProvider(client)], rng=random.Random(4))
        result = await skill.run(LeetCodeArgs(mode="random", difficulty="easy"), _ctx())
    count, fetch = (body["variables"] for body in _bodies(route))
    assert count == {
        "categorySlug": CATEGORY,
        "skip": 0,
        "limit": 1,
        "filters": {"difficulty": "EASY"},
    }
    assert fetch["limit"] == PAGE_SIZE and 0 <= fetch["skip"] <= 810 - PAGE_SIZE
    assert fetch["filters"] == {"difficulty": "EASY"}
    # The members-only problem is never the pick.
    assert result.text == (
        "A random Easy LeetCode problem:\n"
        "#9 Palindrome Number (Easy, 58.0% acceptance)\n"
        "Topics: Array, Hash Table\n"
        "<https://leetcode.com/problems/palindrome-number/>"
    )


@respx.mock
async def test_random_without_a_difficulty_draws_from_every_difficulty() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(3, [_question("1", "Two Sum")])),
            httpx.Response(200, json=_listing(3, [_question("42", "Trapping Rain Water", "Hard")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs(mode="random"), _ctx()
        )
    assert all(body["variables"]["filters"] == {} for body in _bodies(route))
    assert result.text is not None
    assert result.text.startswith("A random LeetCode problem:\n#42 Trapping Rain Water (Hard,")


@respx.mock
async def test_random_offset_near_the_end_still_fetches_a_full_page() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(100, [])),
            httpx.Response(200, json=_listing(100, [_question("1", "Two Sum")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        skill = LeetCodeSkill([GraphQLProvider(client)], rng=_FixedRng(99))
        await skill.run(LeetCodeArgs(mode="random"), _ctx())
    assert _bodies(route)[1]["variables"]["skip"] == 100 - PAGE_SIZE


@respx.mock
async def test_random_with_nothing_free_is_empty() -> None:
    respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(2, [])),
            httpx.Response(200, json=_listing(2, [_question("7", "Locked", paid=True)])),
        ]
    )
    async with httpx.AsyncClient() as client:
        with pytest.raises(EmptyResult, match="no free hard problem"):
            await LeetCodeSkill([GraphQLProvider(client)]).run(
                LeetCodeArgs(mode="random", difficulty="hard"), _ctx()
            )


@respx.mock
async def test_random_from_an_empty_set_is_empty() -> None:
    route = respx.post(GRAPHQL_URL).respond(json=_listing(0, []))
    async with httpx.AsyncClient() as client:
        with pytest.raises(EmptyResult):
            await LeetCodeSkill([GraphQLProvider(client)]).run(LeetCodeArgs(mode="random"), _ctx())
    assert route.call_count == 1


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503),
        # A query LeetCode rejects comes back as HTTP 400 with GraphQL errors...
        httpx.Response(400, json={"errors": [{"message": "Expected type DifficultyEnum"}]}),
        # ...and a partial failure can arrive as 200 with errors alongside the data.
        httpx.Response(200, json={"data": {}, "errors": [{"message": "boom"}]}),
        httpx.Response(200, text="<html>not json</html>"),
        # A daily missing a required field is not an answer.
        httpx.Response(
            200,
            json={
                "data": {
                    "activeDailyCodingChallengeQuestion": {
                        "date": "2026-10-22",
                        "question": {"questionFrontendId": "1"},
                    }
                }
            },
        ),
        httpx.Response(200, json={"data": {"activeDailyCodingChallengeQuestion": None}}),
    ],
)
@respx.mock
async def test_a_failed_or_malformed_answer_is_unavailable(response: httpx.Response) -> None:
    respx.post(GRAPHQL_URL).mock(return_value=response)
    async with httpx.AsyncClient() as client:
        with pytest.raises(UpstreamUnavailable):
            await LeetCodeSkill([GraphQLProvider(client)]).run(LeetCodeArgs(), _ctx())


@respx.mock
async def test_a_transport_error_is_unavailable() -> None:
    respx.post(GRAPHQL_URL).mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as client:
        with pytest.raises(UpstreamUnavailable):
            await LeetCodeSkill([GraphQLProvider(client)]).run(LeetCodeArgs(mode="random"), _ctx())


_TWO_SUM = Problem(
    number="1",
    title="Two Sum",
    slug="two-sum",
    difficulty="Easy",
    acceptance=None,
    topics=(),
    paid_only=False,
)


class _Down(LeetCodeProvider):
    name = "down"

    async def daily(self) -> Daily:
        raise httpx.ConnectError("refused")

    async def random_problem(
        self, difficulty: LeetCodeDifficulty | None, rng: random.Random
    ) -> Problem | None:
        raise httpx.ConnectError("refused")


class _Mirror(LeetCodeProvider):
    name = "mirror"

    def __init__(self, problem: Problem | None) -> None:
        self._problem = problem

    async def daily(self) -> Daily:
        return Daily(date="2026-10-22", problem=_TWO_SUM)

    async def random_problem(
        self, difficulty: LeetCodeDifficulty | None, rng: random.Random
    ) -> Problem | None:
        return self._problem


async def test_a_failing_provider_falls_through_to_the_next() -> None:
    skill = LeetCodeSkill([_Down(), _Mirror(_TWO_SUM)])
    daily = await skill.run(LeetCodeArgs(), _ctx())
    assert daily.text == (
        "LeetCode's daily problem for 2026-10-22:\n#1 Two Sum (Easy)\n"
        "<https://leetcode.com/problems/two-sum/>"
    )
    picked = await skill.run(LeetCodeArgs(mode="random"), _ctx())
    assert picked.text is not None and "#1 Two Sum (Easy)" in picked.text


async def test_an_empty_pick_tries_the_next_provider_before_giving_up() -> None:
    assert (
        await LeetCodeSkill([_Mirror(None), _Mirror(_TWO_SUM)]).run(
            LeetCodeArgs(mode="random"), _ctx()
        )
    ).text is not None
    with pytest.raises(EmptyResult):
        await LeetCodeSkill([_Down(), _Mirror(None)]).run(LeetCodeArgs(mode="random"), _ctx())


def test_the_skill_needs_a_provider() -> None:
    with pytest.raises(ValueError):
        LeetCodeSkill([])
