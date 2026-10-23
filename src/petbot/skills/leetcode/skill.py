"""The ``leetcode`` skill: today's daily problem, or a random free one.

LeetCode publishes no API; the GraphQL endpoint its own site uses answers unauthenticated
reads, and that is what daily-problem bots call (ADR 0013). Providers are ranked like the
web search's: the first that answers wins, so a hosted mirror can be added behind
:class:`LeetCodeProvider` if the endpoint stops answering the deployed runtime.

A random pick is uniform over the algorithms problem set (the problem list without its
database and shell problems): one problem at a random index, drawn again if it is
members-only, which a free account can't open. The endpoint ignores the list's own premium
filter, so that check happens here.
"""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from petbot.domain import EmptyResult, Skill, SkillContext, SkillResult, UpstreamUnavailable
from petbot.types import LeetCodeArgs, LeetCodeDifficulty

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://leetcode.com/graphql/"
PROBLEM_URL = "https://leetcode.com/problems/{slug}/"
#: The problem set a random pick is drawn from.
CATEGORY = "algorithms"
#: Draws before a random pick gives up on landing on a free problem.
MAX_DRAWS = 4
#: Seconds a problem count is reused; it only grows when LeetCode adds a problem.
TOTAL_TTL = 3600.0

_QUESTION_FIELDS = (
    "questionFrontendId title titleSlug difficulty acRate paidOnly: isPaidOnly topicTags { name }"
)
DAILY_QUERY = (
    "query questionOfToday { activeDailyCodingChallengeQuestion { date question { "
    f"{_QUESTION_FIELDS} }} }} }}"
)
LIST_QUERY = (
    "query problemsetQuestionList($categorySlug: String, $limit: Int, $skip: Int, "
    "$filters: QuestionListFilterInput) { problemsetQuestionList: questionList("
    "categorySlug: $categorySlug, limit: $limit, skip: $skip, filters: $filters) { "
    f"total: totalNum questions: data {{ {_QUESTION_FIELDS} }} }} }}"
)


@dataclass(frozen=True)
class Problem:
    """One LeetCode problem, as the skill reports it."""

    number: str
    title: str
    slug: str
    #: As LeetCode spells it: ``Easy``, ``Medium`` or ``Hard``.
    difficulty: str
    #: Accepted submissions as a percentage of all, if LeetCode reports it.
    acceptance: float | None
    topics: tuple[str, ...]
    paid_only: bool

    @property
    def url(self) -> str:
        return PROBLEM_URL.format(slug=self.slug)


@dataclass(frozen=True)
class Daily:
    """The daily problem and the day (``YYYY-MM-DD``) LeetCode dates it."""

    date: str
    problem: Problem


class LeetCodeProvider(Protocol):
    """A source of LeetCode problems. Raises ``httpx.HTTPError`` or ``ValueError`` when it
    can't answer; a random pick is ``None`` when it found no free problem."""

    name: str

    async def daily(self) -> Daily: ...

    async def random_problem(
        self, difficulty: LeetCodeDifficulty | None, rng: random.Random
    ) -> Problem | None: ...


def _text(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"problem without {key}")
    return value


def parse_problem(raw: object) -> Problem:
    """A :class:`Problem` from one GraphQL question object; ``ValueError`` if it isn't one."""
    if not isinstance(raw, dict):
        raise ValueError("problem is not an object")
    acceptance = raw.get("acRate")
    tags = raw.get("topicTags")
    return Problem(
        number=_text(raw, "questionFrontendId"),
        title=_text(raw, "title"),
        slug=_text(raw, "titleSlug"),
        difficulty=_text(raw, "difficulty"),
        acceptance=float(acceptance) if isinstance(acceptance, int | float) else None,
        topics=tuple(
            t["name"]
            for t in (tags if isinstance(tags, list) else [])
            if isinstance(t, dict) and isinstance(t.get("name"), str)
        ),
        paid_only=raw.get("paidOnly") is True,
    )


class GraphQLProvider(LeetCodeProvider):
    """LeetCode's own GraphQL endpoint, read without an account."""

    name = "leetcode-graphql"

    def __init__(
        self, client: httpx.AsyncClient, *, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._client = client
        self._clock = clock
        #: Problem count per difficulty, with when it was read.
        self._totals: dict[LeetCodeDifficulty | None, tuple[int, float]] = {}

    async def _query(self, operation: str, query: str, variables: dict[str, Any]) -> Any:
        response = await self._client.post(
            GRAPHQL_URL,
            json={"operationName": operation, "query": query, "variables": variables},
        )
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict) or body.get("errors"):
            raise ValueError(f"{operation} returned no data")
        return data

    async def daily(self) -> Daily:
        data = await self._query("questionOfToday", DAILY_QUERY, {})
        active = data.get("activeDailyCodingChallengeQuestion")
        if not isinstance(active, dict) or not isinstance(active.get("date"), str):
            raise ValueError("no daily problem")
        return Daily(date=active["date"], problem=parse_problem(active.get("question")))

    async def _page(
        self, difficulty: LeetCodeDifficulty | None, skip: int, limit: int
    ) -> tuple[int, list[Problem]]:
        filters = {"difficulty": difficulty.upper()} if difficulty else {}
        data = await self._query(
            "problemsetQuestionList",
            LIST_QUERY,
            {"categorySlug": CATEGORY, "skip": skip, "limit": limit, "filters": filters},
        )
        listing = data.get("problemsetQuestionList")
        if not isinstance(listing, dict) or not isinstance(listing.get("total"), int):
            raise ValueError("no problem list")
        total: int = listing["total"]
        self._totals[difficulty] = (total, self._clock())
        questions = listing.get("questions")
        problems: list[Problem] = []
        for raw in questions if isinstance(questions, list) else []:
            try:
                problems.append(parse_problem(raw))
            except ValueError:
                # One odd entry (a hidden problem, say) shouldn't sink the rest of the list.
                logger.debug("leetcode: skipped an unreadable problem in the list")
        return total, problems

    async def _total(self, difficulty: LeetCodeDifficulty | None) -> int:
        cached = self._totals.get(difficulty)
        if cached is not None and self._clock() - cached[1] < TOTAL_TTL:
            return cached[0]
        total, _ = await self._page(difficulty, skip=0, limit=1)
        return total

    async def random_problem(
        self, difficulty: LeetCodeDifficulty | None, rng: random.Random
    ) -> Problem | None:
        for _ in range(MAX_DRAWS):
            total = await self._total(difficulty)
            if total <= 0:
                return None
            # Each page read refreshes the count, so a stale one corrects itself.
            _, problems = await self._page(difficulty, skip=rng.randrange(total), limit=1)
            if problems and not problems[0].paid_only:
                return problems[0]
        return None


def _describe(problem: Problem) -> list[str]:
    stats = problem.difficulty
    if problem.acceptance is not None:
        stats += f", {problem.acceptance:.1f}% acceptance"
    lines = [f"#{problem.number} {problem.title} ({stats})"]
    if problem.topics:
        lines.append(f"Topics: {', '.join(problem.topics)}")
    lines.append(f"<{problem.url}>")
    return lines


def format_daily(daily: Daily) -> str:
    """What the reader (the model, or the slash stylist) gets for the daily problem."""
    return "\n".join([f"LeetCode's daily problem for {daily.date}:", *_describe(daily.problem)])


def format_random(problem: Problem, difficulty: LeetCodeDifficulty | None) -> str:
    """What the reader gets for a random pick."""
    kind = f"{difficulty.capitalize()} " if difficulty else ""
    return "\n".join([f"A random {kind}LeetCode problem:", *_describe(problem)])


class LeetCodeSkill(Skill[LeetCodeArgs]):
    """Today's LeetCode daily problem, or a random free one, from the first provider that
    answers."""

    name = "leetcode"
    description = "Look up a LeetCode problem."
    args_model = LeetCodeArgs

    def __init__(
        self, providers: Sequence[LeetCodeProvider], *, rng: random.Random | None = None
    ) -> None:
        if not providers:
            raise ValueError("LeetCodeSkill needs at least one provider")
        self._providers = tuple(providers)
        self._rng = rng or random.Random()

    async def run(self, args: LeetCodeArgs, ctx: SkillContext) -> SkillResult:
        answered = False
        for provider in self._providers:
            try:
                if args.mode == "daily":
                    return SkillResult.message(format_daily(await provider.daily()))
                problem = await provider.random_problem(args.difficulty, self._rng)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("leetcode: %s failed: %s", provider.name, type(exc).__name__)
                continue
            answered = True
            if problem is not None:
                return SkillResult.message(format_random(problem, args.difficulty))
        if not answered:
            raise UpstreamUnavailable("LeetCode isn't answering right now.")
        kind = f"{args.difficulty} " if args.difficulty else ""
        # A miss is a failed draw (members-only problems, or an empty listing), not proof
        # that LeetCode has no free problem of this kind.
        raise EmptyResult(f"I couldn't draw a free {kind}LeetCode problem this time; try again.")
