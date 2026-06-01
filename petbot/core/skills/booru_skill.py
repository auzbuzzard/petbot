"""Booru search skills: ``/derpi`` and ``/e621``.

Both wrap the providers in :mod:`petbot.core.capabilities.boorus`. There is no
explicit *option*: the channel decides the safety floor. ``safe_only`` is set
from ``ctx.capabilities.allows_explicit`` (the Discord adapter fills that from
``channel.is_nsfw()``), so a SFW channel is restricted to safe results and a NSFW
channel sees every rating. The ``sort`` option is typed per site — each skill's
schema ``enum`` is generated from that site's own ``Sort``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import aiohttp

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.capabilities.boorus.engine import run_search
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.http import HttpSession
from petbot.core.capabilities.boorus.types import SearchRequest, parse_tags
from petbot.core.skills.base import Skill
from petbot.core.skills.context import SkillContext, SkillResult

_NETWORK_FAILURE = "uwu the booru didn't answer — please try again in a bit."


def _tags_schema(sort_values: list[str]) -> Mapping[str, Any]:
    return {
        "type": "object",
        "properties": {
            "tags": {"type": "string", "description": "Comma-separated tags to search for."},
            "sort": {
                "type": "string",
                "enum": sort_values,
                "description": "How to order matches before picking one.",
            },
        },
        "required": ["tags"],
        "additionalProperties": False,
    }


class DerpiSkill(Skill):
    """Search Derpibooru for an image matching the given tags."""

    name: ClassVar[str] = "derpi"
    description: ClassVar[str] = "Search Derpibooru for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _tags_schema([s.value for s in derpibooru.Sort])

    def __init__(self, *, session: HttpSession, api_key: str | None = None):
        self._session = session
        self._provider = derpibooru.DerpibooruProvider(api_key=api_key)

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        search = SearchRequest(
            tags=tuple(parse_tags(str(args["tags"]))),
            safe_only=not ctx.capabilities.allows_explicit,
        )
        sort = derpibooru.Sort(str(args.get("sort", derpibooru.Sort.random.value)))
        response = self._provider.request(self._session, search, sort=sort)
        try:
            return await run_search(self._provider, response, search, author=ctx.user.display_name)
        except SiteFailureStatusError as exc:
            return SkillResult.failure(exc.print_message)
        except (aiohttp.ClientError, ValueError):
            return SkillResult.failure(_NETWORK_FAILURE)


class E621Skill(Skill):
    """Search e621 for an image matching the given tags."""

    name: ClassVar[str] = "e621"
    description: ClassVar[str] = "Search e621 for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _tags_schema([s.value for s in e621.Sort])

    def __init__(
        self,
        *,
        session: HttpSession,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ):
        self._session = session
        self._provider = e621.E621Provider(
            user_agent=user_agent, username=username, api_key=api_key
        )

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        search = SearchRequest(
            tags=tuple(parse_tags(str(args["tags"]))),
            safe_only=not ctx.capabilities.allows_explicit,
        )
        sort = e621.Sort(str(args.get("sort", e621.Sort.random.value)))
        response = self._provider.request(self._session, search, sort=sort)
        try:
            return await run_search(self._provider, response, search, author=ctx.user.display_name)
        except SiteFailureStatusError as exc:
            return SkillResult.failure(exc.print_message)
        except (aiohttp.ClientError, ValueError):
            return SkillResult.failure(_NETWORK_FAILURE)
