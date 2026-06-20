"""Booru search skills: ``derpi``, ``furbooru``, and ``e621``.

Derpibooru and Furbooru both run Philomena; they share a ``_PhilomenaSkill``
base whose only variable is the factory function that builds the provider.
e621 uses a completely different API and keeps its own concrete class.

There is no explicit safety option: the channel decides the safety floor
(``safe_only`` comes from ``ctx.allows_explicit``, which the edge fills from
``channel.is_nsfw()``).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import httpx

from petbot.domain import Skill, SkillContext, SkillResult
from petbot.skills.booru import derpibooru, e621, furbooru
from petbot.skills.booru.base import BooruProvider
from petbot.skills.booru.engine import run_search
from petbot.skills.booru.errors import SiteFailureStatusError
from petbot.skills.booru.tags import NumericFilter, Sort
from petbot.skills.booru.types import SearchRequest
from petbot.types import BooruArgs

logger = logging.getLogger(__name__)

_NETWORK_FAILURE = "uwu the booru didn't answer — please try again in a bit."


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
    # The boundary that *handles* a failed search (turns it into a SkillResult),
    # so it's the one place that logs it — at a level matching severity.
    try:
        return await run_search(provider, client, search, author=ctx.user.display_name)
    except SiteFailureStatusError as exc:
        logger.debug("%s rejected the search: %s", provider.name, exc.site_message)
        return SkillResult.failure(exc.print_message)
    except (httpx.HTTPError, ValueError):
        logger.warning("%s search failed to reach/parse the site", provider.name, exc_info=True)
        return SkillResult.failure(_NETWORK_FAILURE)


# Philomena sites (Derpibooru, Furbooru) share the same skill shape; only the
# provider factory differs.
class _PhilomenaSkill(Skill[BooruArgs]):
    """Shared base for every Philomena-backed search skill."""

    args_model = BooruArgs
    _provider_factory: Callable[..., BooruProvider]

    def __init__(self, *, client: httpx.AsyncClient, api_key: str | None = None) -> None:
        self._client = client
        self._provider: BooruProvider = type(self)._provider_factory(api_key=api_key)

    async def run(self, args: BooruArgs, ctx: SkillContext) -> SkillResult:
        return await _run(self._provider, self._client, args, ctx)


class DerpiSkill(_PhilomenaSkill):
    """Search Derpibooru for an image matching the given tags."""

    name = "derpi"
    description = "Search Derpibooru for an image matching the given tags."
    _provider_factory = derpibooru.DerpibooruProvider


class FurbooruSkill(_PhilomenaSkill):
    """Search Furbooru for an image matching the given tags."""

    name = "furbooru"
    description = "Search Furbooru for an image matching the given tags."
    _provider_factory = furbooru.FurbooruProvider


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
