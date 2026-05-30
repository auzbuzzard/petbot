"""e621 / e926 provider (furry imageboard), modernized.

Endpoint moved from ``/post/index.json`` to ``/posts.json`` (response:
``{"posts": [...]}``) with a nested post schema. A descriptive User-Agent is now
mandatory — browser-spoofing UAs are blocked — and optional ``username``/
``api_key`` HTTP basic auth raises rate limits. Explicit content uses e621; the
safe mirror e926 is used otherwise. Returns a neutral ``SkillResult``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

import aiohttp

from petbot.core.capabilities.boorus import datastruct, errors
from petbot.core.skills.context import EmbedSpec, SkillResult

_ARG_PATTERN = re.compile(r"--([\w:]+)")

_EXPLICIT_ROOT = "https://e621.net/"
_SAFE_ROOT = "https://e926.net/"

_COLOR_SAFE = 0x00FF00
_COLOR_QUESTIONABLE = 0xFFFF00
_COLOR_EXPLICIT = 0xFF0000


class Rating(Enum):
    safe = "s"
    questionable = "q"
    explicit = "e"


def root_url(*, explicit: bool) -> str:
    return _EXPLICIT_ROOT if explicit else _SAFE_ROOT


def site_name(*, explicit: bool) -> str:
    return "e621" if explicit else "e926"


class ImageResult(datastruct.Result):
    """A single e621 post, reading the modern nested schema."""

    def __init__(self, data: Mapping[str, Any]):
        super().__init__(data)
        file_block: Mapping[str, Any] = data.get("file", {})
        sample_block: Mapping[str, Any] = data.get("sample", {})
        score_block: Mapping[str, Any] = data.get("score", {})

        self.post_id: int = int(data.get("id", 0))
        self.file_ext: str = str(file_block.get("ext", ""))
        self.file_url: str = str(file_block.get("url") or "")
        self.sample_url: str = str(sample_block.get("url") or self.file_url)
        self.score_total: int = int(score_block.get("total", 0))
        self.fav_count: int = int(data.get("fav_count", 0))
        self.rating = self._rating(str(data.get("rating", "")))

    @staticmethod
    def _rating(raw: str) -> Rating | None:
        try:
            return Rating(raw)
        except ValueError:
            return None

    @property
    def is_explicit(self) -> bool:
        return self.rating is not Rating.safe


class SearchQuery(datastruct.SearchQuery):
    def __init__(
        self,
        tags: Sequence[str],
        args: Mapping[str, Any],
        *,
        session: datastruct.HttpSession,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ):
        super().__init__(tags, args, session=session)
        self._user_agent = user_agent
        self._username = username
        self._api_key = api_key

    def endpoint(self) -> str:
        return root_url(explicit=self.is_explicit) + "posts.json"

    def headers(self) -> dict[str, str]:
        # e621 mandates a descriptive, non-browser User-Agent.
        return {"User-Agent": self._user_agent}

    def auth(self) -> aiohttp.BasicAuth | None:
        if self._username and self._api_key:
            return aiohttp.BasicAuth(self._username, self._api_key)
        return None

    def params(self) -> dict[str, Any]:
        query_tags = [*self.tags, "order:random"]
        return {"tags": " ".join(query_tags), "limit": 1}

    def web_url(self) -> str:
        joined = "+".join(tag.replace(" ", "_") for tag in self.tags)
        return f"{root_url(explicit=self.is_explicit)}posts?tags={joined}"


def parse_args(message: str) -> tuple[dict[str, Any], list[str]]:
    """Split a raw query into ``(args, tags)``. ``--e`` requests explicit."""
    flags = set(_ARG_PATTERN.findall(message))
    args: dict[str, Any] = {"explicit": "e" in flags}
    cleaned = _ARG_PATTERN.sub("", message)
    tags = [tag.strip() for tag in cleaned.split(",") if tag.strip()]
    return args, tags


def image(json_dict: Mapping[str, Any]) -> ImageResult | None:
    """Extract the first post, raising on an explicit site failure payload."""
    if json_dict.get("success") is False:
        reason = json_dict.get("reason") or json_dict.get("message")
        raise errors.SiteFailureStatusError(
            site_message=str(reason or ""),
            print_message=(
                f"uwu I couldn't do that. e621 says: {reason}"
                if reason
                else "uwu I couldn't do that — e621 said something I didn't understand ;~;"
            ),
        )
    posts = json_dict.get("posts") or []
    if not posts:
        return None
    return ImageResult(posts[0])


def build_result(
    query: SearchQuery,
    result: ImageResult | None,
    *,
    author: str,
) -> SkillResult:
    """Turn a parsed post into a neutral :class:`SkillResult`."""
    if result is None:
        text = datastruct.result_greeter(
            has_image=False, is_explicit=query.is_explicit, author=author
        )
        return SkillResult.message(text.format(tags=", ".join(query.tags)))

    greeter = datastruct.result_greeter(
        has_image=True, is_explicit=result.is_explicit, author=author
    )
    explicit = result.is_explicit
    name = site_name(explicit=explicit)
    root = root_url(explicit=explicit)
    color = (
        _COLOR_SAFE
        if result.rating is Rating.safe
        else _COLOR_QUESTIONABLE
        if result.rating is Rating.questionable
        else _COLOR_EXPLICIT
    )
    description = (
        f"score: {result.score_total} | faves: {result.fav_count} | "
        f"source: [{name}]({root}posts/{result.post_id}) | filetype: {result.file_ext}"
    )
    embed = EmbedSpec(
        title=f"results: {', '.join(query.tags)}",
        description=description,
        url=query.web_url(),
        color=color,
        image_url=result.sample_url,
        author_name=name,
        author_url=root,
        author_icon_url="https://e621.net/favicon-32x32.png",
    )
    return SkillResult.message(greeter, embed=embed)


async def search(
    message: str,
    *,
    session: datastruct.HttpSession,
    allows_explicit: bool,
    author: str,
    user_agent: str,
    username: str | None = None,
    api_key: str | None = None,
) -> SkillResult:
    """Parse, query, and render an e621/e926 search into a ``SkillResult``."""
    args, tags = parse_args(message)
    if args.get("explicit") and not allows_explicit:
        return SkillResult.failure(
            "Explicit results are only available in age-restricted (NSFW) channels."
        )
    query = SearchQuery(
        tags,
        args,
        session=session,
        user_agent=user_agent,
        username=username,
        api_key=api_key,
    )
    payload = await query.request()
    return build_result(query, image(payload), author=author)
