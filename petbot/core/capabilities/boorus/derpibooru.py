"""Derpibooru provider (My Little Pony imageboard), modernized to API v1.

Endpoint moved from the legacy ``/search.json`` to
``/api/v1/json/search/images`` (response: ``{"images": [...], "total": N}``).
Optional ``key`` raises rate limits. Returns a neutral ``SkillResult``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any

from petbot.core.capabilities.boorus import datastruct
from petbot.core.skills.context import EmbedSpec, SkillResult

ROOT_URL = "https://derpibooru.org/"
API_URL = "https://derpibooru.org/api/v1/json/search/images"
_ARG_PATTERN = re.compile(r"--([\w:]+)")

# Filter IDs control which content the API may return.
_FILTERS = {"everything": "56027", "steady": "150237", "default": "100073"}

# Embed accent colors per rating.
_COLOR_SAFE = 0x00FF00
_COLOR_SUGGESTIVE = 0x0000FF
_COLOR_QUESTIONABLE = 0xFFFF00
_COLOR_EXPLICIT = 0xFF0000


class Rating(Enum):
    safe = "safe"
    suggestive = "suggestive"
    questionable = "questionable"
    explicit = "explicit"


_RATING_COLOR = {
    Rating.safe: _COLOR_SAFE,
    Rating.suggestive: _COLOR_SUGGESTIVE,
    Rating.questionable: _COLOR_QUESTIONABLE,
    Rating.explicit: _COLOR_EXPLICIT,
}


class Order(Enum):
    creation_date = "created_at"
    score = "score"
    wilson_score = "wilson_score"
    relevance = "relevance"
    comments = "comments"
    random = "random"


class ImageResult(datastruct.Result):
    """A single Derpibooru image.

    Rating is derived from the image's tag *names* (robust across API versions),
    and the preview image prefers ``view_url`` then the ``large`` representation.
    """

    id: int
    score: int
    faves: int
    format: str
    tags: list[str]
    representations: Mapping[str, str]
    view_url: str

    def __init__(self, data: Mapping[str, Any]):
        super().__init__(data)
        self.rating = self._rating()

    def _rating(self) -> Rating | None:
        tags = {str(t).lower() for t in getattr(self, "tags", [])}
        for rating in (Rating.safe, Rating.suggestive, Rating.questionable, Rating.explicit):
            if rating.value in tags:
                return rating
        return None

    @property
    def is_explicit(self) -> bool:
        return self.rating is Rating.explicit

    @property
    def image_url(self) -> str:
        if getattr(self, "view_url", None):
            return self.view_url
        return self.representations.get("large", "")


class SearchQuery(datastruct.SearchQuery):
    def __init__(
        self,
        tags: Sequence[str],
        args: Mapping[str, Any],
        *,
        session: datastruct.HttpSession,
        api_key: str | None = None,
    ):
        super().__init__(tags, args, session=session)
        self.order: Order = args.get("order", Order.random)
        self.is_desc_order: bool = args.get("sort", True)
        self._api_key = api_key

    def endpoint(self) -> str:
        return API_URL

    def params(self) -> dict[str, Any]:
        if self.args.get("filter") == "everything":
            filter_id = _FILTERS["everything"]
        elif self.is_explicit:
            filter_id = _FILTERS["steady"]
        else:
            filter_id = _FILTERS["default"]
        params: dict[str, Any] = {
            "q": ",".join(self.tags) or "*",
            "sf": self.order.value,
            "sd": "desc" if self.is_desc_order else "asc",
            "filter_id": filter_id,
            "per_page": 1,
        }
        if self._api_key:
            params["key"] = self._api_key
        return params

    def web_url(self) -> str:
        joined = ",".join(tag.replace(" ", "+") for tag in self.tags)
        return f"{ROOT_URL}search?q={joined}"


def parse_args(message: str) -> tuple[dict[str, Any], list[str]]:
    """Split a raw query into ``(args, tags)``.

    Flags use ``--flag`` syntax (e.g. ``--e`` for explicit, ``--sort_score``).
    """
    flags = set(_ARG_PATTERN.findall(message))
    args: dict[str, Any] = {"order": Order.random, "explicit": False}

    if "e" in flags:
        args["explicit"] = True
    if "sort_new" in flags:
        args["order"] = Order.creation_date
    if flags & {"sort_relevance", "sort_rel"}:
        args["order"] = Order.relevance
    if "sort_score" in flags:
        args["order"] = Order.score
    if "sort_wscore" in flags:
        args["order"] = Order.wilson_score
    if "sort_comments" in flags:
        args["order"] = Order.comments
    if flags & {"filter_everything", "f_everything"}:
        args["filter"] = "everything"

    cleaned = _ARG_PATTERN.sub("", message)
    tags = [tag.strip() for tag in cleaned.split(",") if tag.strip()]
    return args, tags


def image(json_dict: Mapping[str, Any]) -> tuple[ImageResult | None, int]:
    """Extract the first image and the total match count from a response."""
    images = json_dict.get("images") or []
    total = int(json_dict.get("total", len(images)))
    if not images:
        return None, 0
    return ImageResult(images[0]), total


def build_result(
    query: SearchQuery,
    found: tuple[ImageResult | None, int],
    *,
    author: str,
) -> SkillResult:
    """Turn a parsed search outcome into a neutral :class:`SkillResult`."""
    result, count = found
    if result is None or count == 0:
        text = datastruct.result_greeter(
            has_image=False, is_explicit=query.is_explicit, author=author
        )
        return SkillResult.message(text.format(tags=", ".join(query.tags)))

    greeter = datastruct.result_greeter(
        has_image=True, is_explicit=result.is_explicit, author=author
    )
    tags_label = _tags_label(query.tags)
    description = (
        f"score: {result.score} | faves: {result.faves} | "
        f"source: [derpibooru]({ROOT_URL}{result.id}) | filetype: {result.format}"
    )
    embed = EmbedSpec(
        title=f"{count} result{'s' if count != 1 else ''}: {tags_label}",
        description=description,
        url=query.web_url(),
        color=_RATING_COLOR.get(result.rating) if result.rating else None,
        image_url=result.image_url,
        author_name="Derpibooru",
        author_url=ROOT_URL,
        author_icon_url="https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg",
    )
    return SkillResult.message(greeter, embed=embed)


def _tags_label(tags: Sequence[str], *, limit: int = 256) -> str:
    label = ", ".join(tags)
    if len(label) <= limit:
        return label
    truncated: list[str] = []
    used = 0
    for tag in tags:
        if used + len(tag) + 2 > limit:
            break
        truncated.append(tag)
        used += len(tag) + 2
    return ", ".join(truncated) + " …"


async def search(
    message: str,
    *,
    session: datastruct.HttpSession,
    allows_explicit: bool,
    author: str,
    api_key: str | None = None,
) -> SkillResult:
    """Parse, query, and render a Derpibooru search into a ``SkillResult``.

    Explicit content is requested only when the caller's context permits it.
    """
    args, tags = parse_args(message)
    if args.get("explicit") and not allows_explicit:
        return SkillResult.failure(
            "Explicit results are only available in age-restricted (NSFW) channels."
        )
    query = SearchQuery(tags, args, session=session, api_key=api_key)
    payload = await query.request()
    return build_result(query, image(payload), author=author)
