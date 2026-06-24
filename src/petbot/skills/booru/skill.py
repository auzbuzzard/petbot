"""Booru search skills: ``derpi`` and ``e621``.

Both wrap a provider in this package's engine. There is no explicit *option*: the
channel decides the safety floor (``safe_only`` comes from ``ctx.allows_explicit``,
which the frontend fills from ``channel.is_nsfw()``). The other options — ``sort``,
``file_type``, ``min_score`` — map onto each provider's full native vocabulary.
"""

from __future__ import annotations

import logging

import httpx
from opentelemetry import metrics, trace

from petbot.domain import EmptyResult, Skill, SkillContext, SkillResult, UpstreamUnavailable
from petbot.skills.booru import derpibooru, e621
from petbot.skills.booru.base import BooruProvider
from petbot.skills.booru.engine import run_search
from petbot.skills.booru.errors import SiteFailureStatusError
from petbot.skills.booru.tags import NumericFilter, Sort
from petbot.skills.booru.types import SearchRequest
from petbot.types import BooruArgs

logger = logging.getLogger(__name__)

_NETWORK_FAILURE = "uwu the booru didn't answer — please try again in a bit."

# A non-content outcome signal: the exact failure class behind the e621 incident ("called
# the tool, got nothing back, why?") becomes a span attribute + counter. The tags/result are
# never recorded — only the coarse status.
_meter = metrics.get_meter("petbot.skills.booru")
_OUTCOMES = _meter.create_counter(
    "petbot.booru.outcome", description="Booru searches by provider + outcome status."
)


def _record_outcome(provider: str, status: str) -> None:
    """Tag the active tool span with the coarse outcome and bump the counter.
    ``status`` ∈ ``ok | empty | safe_limited | error``."""
    trace.get_current_span().set_attribute("petbot.booru.outcome", status)
    _OUTCOMES.add(1, {"provider": provider, "status": status})


def _default_sort(provider: BooruProvider) -> Sort | None:
    """The ordering used when the caller names none: ``random``, so a bare search
    returns a *different* image each time. The guard keeps this safe if a future
    provider's vocabulary ever lacks a ``random`` order."""
    try:
        return provider.Sort("random")
    except ValueError:
        return None


def _build_search(provider: BooruProvider, args: BooruArgs, ctx: SkillContext) -> SearchRequest:
    sort = provider.Sort(args.sort) if args.sort else _default_sort(provider)
    file_type = provider.FileType(args.file_type) if args.file_type else None
    score = NumericFilter(at_least=args.min_score) if args.min_score is not None else None
    return SearchRequest(
        tags=provider.parse_tags(args.tags),
        safe_only=not ctx.allows_explicit,
        sort=sort,
        descending=args.descending,
        file_type=file_type,
        score=score,
    )


async def _run(
    provider: BooruProvider,
    client: httpx.AsyncClient,
    args: BooruArgs,
    ctx: SkillContext,
) -> SkillResult:
    search = _build_search(provider, args, ctx)
    # The one place that logs a search failure (at a level matching severity) before
    # re-raising it as a neutral SkillError the process boundary voices, and the one place
    # that records the coarse outcome signal. An empty search raises EmptyResult and still
    # propagates untouched — we only tag it on the way past.
    try:
        result = await run_search(provider, client, search)
    except EmptyResult:
        _record_outcome(provider.name, "safe_limited" if search.safe_only else "empty")
        raise
    except SiteFailureStatusError as exc:
        _record_outcome(provider.name, "error")
        logger.debug("%s rejected the search: %s", provider.name, exc.site_message)
        raise UpstreamUnavailable(exc.print_message) from exc
    except (httpx.HTTPError, ValueError) as exc:
        _record_outcome(provider.name, "error")
        logger.warning("%s search failed to reach/parse the site", provider.name, exc_info=True)
        raise UpstreamUnavailable(_NETWORK_FAILURE) from exc
    else:
        _record_outcome(provider.name, "ok")
        return result


class DerpiSkill(Skill[BooruArgs]):
    """Search Derpibooru for an image matching the given tags."""

    name = "derpi"
    description = "Search Derpibooru for an image matching the given tags."
    args_model = BooruArgs

    def __init__(self, *, client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._client = client
        self._provider = derpibooru.DerpibooruProvider(api_key=api_key)

    async def run(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await _run(self._provider, self._client, args, ctx)


class E621Skill(Skill[BooruArgs]):
    """Search e621 for an image matching the given tags."""

    name = "e621"
    description = "Search e621 for an image matching the given tags."
    args_model = BooruArgs

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._client = client
        self._provider = e621.E621Provider(
            user_agent=user_agent, username=username, api_key=api_key
        )

    async def run(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await _run(self._provider, self._client, args, ctx)
