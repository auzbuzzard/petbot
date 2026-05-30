"""Booru search skills: ``/derpi`` and ``/e621``.

Both wrap the modernized providers in :mod:`petbot.core.capabilities.boorus`.
Explicit content is gated on ``ctx.capabilities.allows_explicit`` — the skill
never inspects the platform, only the capability flag the adapter set.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar

import aiohttp

from petbot.core.capabilities.boorus import datastruct, derpibooru, e621
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.skills.base import Skill
from petbot.core.skills.context import SkillContext, SkillResult

_TAGS_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "tags": {
            "type": "string",
            "description": (
                "Comma-separated tags to search for. Flags like --e (explicit) "
                "or --sort_score may be included."
            ),
        },
    },
    "required": ["tags"],
    "additionalProperties": False,
}

_NETWORK_FAILURE = "uwu the booru didn't answer — please try again in a bit."


class DerpiSkill(Skill):
    """Search Derpibooru for an image matching the given tags."""

    name: ClassVar[str] = "derpi"
    description: ClassVar[str] = "Search Derpibooru for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _TAGS_SCHEMA

    def __init__(self, *, session: datastruct.HttpSession, api_key: str | None = None):
        self._session = session
        self._api_key = api_key

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        try:
            return await derpibooru.search(
                str(args["tags"]),
                session=self._session,
                allows_explicit=ctx.capabilities.allows_explicit,
                author=ctx.user.display_name,
                api_key=self._api_key,
            )
        except SiteFailureStatusError as exc:
            return SkillResult.failure(exc.print_message)
        except aiohttp.ClientError:
            return SkillResult.failure(_NETWORK_FAILURE)


class E621Skill(Skill):
    """Search e621/e926 for an image matching the given tags."""

    name: ClassVar[str] = "e621"
    description: ClassVar[str] = "Search e621/e926 for an image matching the given tags."
    input_schema: ClassVar[Mapping[str, Any]] = _TAGS_SCHEMA

    def __init__(
        self,
        *,
        session: datastruct.HttpSession,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ):
        self._session = session
        self._user_agent = user_agent
        self._username = username
        self._api_key = api_key

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        try:
            return await e621.search(
                str(args["tags"]),
                session=self._session,
                allows_explicit=ctx.capabilities.allows_explicit,
                author=ctx.user.display_name,
                user_agent=self._user_agent,
                username=self._username,
                api_key=self._api_key,
            )
        except SiteFailureStatusError as exc:
            return SkillResult.failure(exc.print_message)
        except aiohttp.ClientError:
            return SkillResult.failure(_NETWORK_FAILURE)
