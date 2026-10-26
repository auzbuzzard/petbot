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
    MAX_DRAWS,
    TOTAL_TTL,
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
    def __init__(self, offset: int) -> None:
        super().__init__()
        self._offset = offset

    def randrange(self, *args: Any, **kwargs: Any) -> int:
        return self._offset


def _bodies(route: respx.Route) -> list[dict[str, Any]]:
    return [json.loads(call.request.content) for call in route.calls]


@respx.mock
async def test_daily_reports_the_dated_problem_with_its_difficulty_and_link() -> None:
    route = respx.post(GRAPHQL_URL).respond(json=_DAILY)
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs(mode="daily"), _ctx()
        )
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
async def test_random_draws_one_problem_at_a_uniform_index_of_its_difficulty() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(810, [_question("1", "Two Sum")])),
            httpx.Response(200, json=_listing(810, [_question("9", "Palindrome Number")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        skill = LeetCodeSkill([GraphQLProvider(client)], rng=_FixedRng(417))
        result = await skill.run(LeetCodeArgs(mode="random", difficulty="easy"), _ctx())
    count, draw = (body["variables"] for body in _bodies(route))
    easy = {"categorySlug": CATEGORY, "filters": {"difficulty": "EASY"}, "limit": 1}
    assert count == {**easy, "skip": 0}
    assert draw == {**easy, "skip": 417}
    assert result.text == (
        "A random Easy LeetCode problem:\n"
        "#9 Palindrome Number (Easy, 58.0% acceptance)\n"
        "Topics: Array, Hash Table\n"
        "<https://leetcode.com/problems/palindrome-number/>"
    )


@respx.mock
async def test_a_members_only_draw_is_drawn_again() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(810, [])),
            httpx.Response(200, json=_listing(810, [_question("7", "Locked", paid=True)])),
            httpx.Response(200, json=_listing(810, [_question("9", "Palindrome Number")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs(mode="random"), _ctx()
        )
    assert route.call_count == 3
    assert result.text is not None and "#9 Palindrome Number" in result.text


@respx.mock
async def test_a_random_problem_of_a_difficulty_given_leetcodes_spelling() -> None:
    route = respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(3, [])),
            httpx.Response(200, json=_listing(3, [_question("42", "Trapping Rain Water", "Hard")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs.model_validate({"mode": "random", "difficulty": "Hard"}), _ctx()
        )
    assert {body["operationName"] for body in _bodies(route)} == {"problemsetQuestionList"}
    assert _bodies(route)[0]["variables"]["filters"] == {"difficulty": "HARD"}
    assert result.text is not None and result.text.startswith("A random Hard LeetCode problem:")


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
async def test_an_unreadable_listed_problem_is_skipped_not_fatal() -> None:
    hidden = {"questionFrontendId": "5", "title": None, "titleSlug": None}
    respx.post(GRAPHQL_URL).mock(
        side_effect=[
            httpx.Response(200, json=_listing(810, [hidden])),
            httpx.Response(200, json=_listing(810, [hidden])),
            httpx.Response(200, json=_listing(810, [_question("9", "Palindrome Number")])),
        ]
    )
    async with httpx.AsyncClient() as client:
        result = await LeetCodeSkill([GraphQLProvider(client)]).run(
            LeetCodeArgs(mode="random"), _ctx()
        )
    assert result.text is not None and "#9 Palindrome Number" in result.text


@respx.mock
async def test_random_that_never_lands_on_a_free_problem_is_a_failed_draw() -> None:
    locked = httpx.Response(200, json=_listing(2, [_question("7", "Locked", paid=True)]))
    route = respx.post(GRAPHQL_URL).mock(return_value=locked)
    async with httpx.AsyncClient() as client:
        # Worded as a missed draw, never as "LeetCode has no free hard problem".
        with pytest.raises(EmptyResult, match="couldn't draw a free hard LeetCode problem"):
            await LeetCodeSkill([GraphQLProvider(client)]).run(
                LeetCodeArgs(mode="random", difficulty="hard"), _ctx()
            )
    assert route.call_count == 1 + MAX_DRAWS


@respx.mock
async def test_the_problem_count_is_reused_until_it_goes_stale() -> None:
    route = respx.post(GRAPHQL_URL).respond(
        json=_listing(810, [_question("9", "Palindrome Number")])
    )
    now = [0.0]
    async with httpx.AsyncClient() as client:
        skill = LeetCodeSkill([GraphQLProvider(client, clock=lambda: now[0])])
        await skill.run(LeetCodeArgs(mode="random"), _ctx())
        assert route.call_count == 2
        await skill.run(LeetCodeArgs(mode="random"), _ctx())
        assert route.call_count == 3
        now[0] += TOTAL_TTL + 1
        await skill.run(LeetCodeArgs(mode="random"), _ctx())
        assert route.call_count == 5


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
        httpx.Response(400, json={"errors": [{"message": "Expected type DifficultyEnum"}]}),
        httpx.Response(200, json={"data": {}, "errors": [{"message": "boom"}]}),
        httpx.Response(200, text="<html>not json</html>"),
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
            await LeetCodeSkill([GraphQLProvider(client)]).run(LeetCodeArgs(mode="daily"), _ctx())


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
    daily = await skill.run(LeetCodeArgs(mode="daily"), _ctx())
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
