"""Booru search skills: ``/derpi`` and ``/e621``.

Both wrap a provider in :mod:`petbot.core.capabilities.boorus`. There is no
explicit *option*: the channel decides the safety floor (``safe_only`` is set
from ``ctx.capabilities.allows_explicit``, which the Discord adapter fills from
``channel.is_nsfw()``). The other options — ``sort``, ``file_type``,
``min_score`` — map onto each provider's full native vocabulary.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, ClassVar

import httpx

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.capabilities.boorus.base import BooruProvider
from petbot.core.capabilities.boorus.engine import run_search
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.tags import FileType, NumericFilter, Sort
from petbot.core.capabilities.boorus.types import SearchRequest
from petbot.core.skills.base import Skill
from petbot.core.skills.context import SkillContext, SkillResult

logger = logging.getLogger(__name__)

_NETWORK_FAILURE = "uwu the booru didn't answer — please try again in a bit."


def _schema(
    *, sort: type[Sort], file_type: type[FileType], tags_desc: str, direction: bool
) -> Mapping[str, Any]:
    properties: dict[str, Any] = {
        "tags": {"type": "string", "description": tags_desc},
        "sort": {
            "type": "string",
            "enum": [m.value for m in sort],
            "description": "How to order matches before picking one.",
        },
        "file_type": {
            "type": "string",
            "enum": [m.value for m in file_type],
            "description": "Restrict results to a file type.",
        },
        "min_score": {
            "type": "integer",
            "minimum": 0,
            "description": "Only results with at least this score.",
        },
    }
    if direction:  # only sites with a separate direction axis (Derpibooru `sd`)
        properties["descending"] = {
            "type": "boolean",
            "description": "Sort descending (default) or ascending.",
        }
    return {
        "type": "object",
        "properties": properties,
        "required": ["tags"],
        "additionalProperties": False,
    }


def _build_search(
    provider: BooruProvider, args: Mapping[str, Any], ctx: SkillContext
) -> SearchRequest:
    sort = provider.Sort(str(args["sort"])) if args.get("sort") else None
    file_type = provider.FileType(str(args["file_type"])) if args.get("file_type") else None
    min_score = args.get("min_score")
    score = NumericFilter(at_least=int(min_score)) if min_score is not None else None
    return SearchRequest(
        tags=provider.parse_tags(str(args["tags"])),
        safe_only=not ctx.capabilities.allows_explicit,
        sort=sort,
        descending=bool(args.get("descending", True)),
        file_type=file_type,
        score=score,
    )


async def _run(
    provider: BooruProvider,
    client: httpx.AsyncClient,
    args: Mapping[str, Any],
    ctx: SkillContext,
) -> SkillResult:
    search = _build_search(provider, args, ctx)
    # This is the boundary that *handles* a failed search (turns it into a
    # SkillResult), so it's the one place that logs it — at a level that matches
    # severity, with a traceback only where one helps.
    try:
        return await run_search(provider, client, search, author=ctx.user.display_name)
    except SiteFailureStatusError as exc:
        # Expected, fully handled, and shown to the user — not a bug. A DEBUG
        # breadcrumb is enough; no traceback.
        logger.debug("%s rejected the search: %s", provider.name, exc.site_message)
        return SkillResult.failure(exc.print_message)
    except (httpx.HTTPError, ValueError):
        # Unexpected: we couldn't reach or decode the site. Capture the traceback.
        logger.warning("%s search failed to reach/parse the site", provider.name, exc_info=True)
        return SkillResult.failure(_NETWORK_FAILURE)


class DerpiSkill(Skill):
    """Search Derpibooru for an image matching the given tags."""

    name: ClassVar[str] = "derpi"
    description: ClassVar[str] = "Search Derpibooru for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _schema(
        sort=derpibooru.Sort,
        file_type=derpibooru.FileType,
        tags_desc="Comma-separated tags (spaces allowed within a tag).",
        direction=True,
    )

    def __init__(self, *, client: httpx.AsyncClient, api_key: str | None = None):
        self._client = client
        self._provider = derpibooru.DerpibooruProvider(api_key=api_key)

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        return await _run(self._provider, self._client, args, ctx)


class E621Skill(Skill):
    """Search e621 for an image matching the given tags."""

    name: ClassVar[str] = "e621"
    description: ClassVar[str] = "Search e621 for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _schema(
        sort=e621.Sort,
        file_type=e621.FileType,
        tags_desc="Space-separated tags (use underscores within a tag, e.g. twilight_sparkle).",
        direction=False,
    )

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ):
        self._client = client
        self._provider = e621.E621Provider(
            user_agent=user_agent, username=username, api_key=api_key
        )

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        return await _run(self._provider, self._client, args, ctx)
