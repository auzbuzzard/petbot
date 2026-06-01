"""Derpibooru provider (My Little Pony imageboard), API v1.

Endpoint ``/api/v1/json/search/images`` → ``{"total": N, "images": [...]}``.
Rating is derived from the image's tag *names* (robust across API versions). The
``safe`` rating term is the only content gate; the "everything" filter is always
used so a NSFW channel sees every rating and a SFW channel is constrained purely
by the injected ``safe`` term. An error body is a 400 ``{"error": "..."}``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from petbot.core.capabilities.boorus.base import BooruResponse, ErrorResponse
from petbot.core.capabilities.boorus.http import HttpResponseContext, HttpSession
from petbot.core.capabilities.boorus.types import Post, SearchRequest


class Sort(StrEnum):
    random = "random"
    score = "score"
    wilson = "wilson_score"
    relevance = "relevance"
    newest = "created_at"
    comments = "comments"


class Rating(StrEnum):
    safe = "safe"
    suggestive = "suggestive"
    questionable = "questionable"
    explicit = "explicit"


_COLOR = {
    Rating.safe: 0x00FF00,
    Rating.suggestive: 0x0000FF,
    Rating.questionable: 0xFFFF00,
    Rating.explicit: 0xFF0000,
}
_NAME = "Derpibooru"
_ROOT = "https://derpibooru.org/"
_ICON = "https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg"


def _rating(tags: list[str]) -> Rating:
    # Derpibooru rating tags are mutually exclusive; `reversed` makes the most
    # explicit one win on the off chance several are present, defaulting to safe.
    names = {tag.lower() for tag in tags}
    return next((r for r in reversed(Rating) if r.value in names), Rating.safe)


class _Repr(BaseModel):
    large: str | None = None


class _Image(BaseModel):
    id: int
    score: int = 0
    faves: int = 0
    format: str = ""
    tags: list[str] = Field(default_factory=list)
    representations: _Repr = Field(default_factory=_Repr)
    view_url: str | None = None


class Response(BooruResponse):
    total: int = 0
    images: list[_Image] = Field(default_factory=list)

    def to_post(self) -> Post | None:
        if not self.images:
            return None
        img = self.images[0]
        url = img.view_url or img.representations.large
        if not url:
            return None
        rating = _rating(img.tags)
        return Post(
            post_id=img.id,
            image_url=url,
            color=_COLOR[rating],
            is_safe=rating is Rating.safe,
            score=img.score,
            favorites=img.faves,
            file_ext=img.format,
            page_url=f"{_ROOT}{img.id}",
            site_name=_NAME,
            site_root=_ROOT,
            site_icon_url=_ICON,
            total=self.total,
        )


class Error(ErrorResponse):
    error: str | None = None  # only present on 400 bodies

    def reason(self) -> str | None:
        return self.error


class DerpibooruProvider:
    name: str = _NAME
    response_model: type[BooruResponse] = Response
    error_model: type[ErrorResponse] = Error

    _API = "https://derpibooru.org/api/v1/json/search/images"
    _FILTER_EVERYTHING = "56027"  # show all ratings; the `safe` term is the only gate

    def __init__(self, *, api_key: str | None = None):
        self._api_key = api_key

    def request(
        self,
        session: HttpSession,
        search: SearchRequest,
        *,
        sort: Sort = Sort.random,
    ) -> HttpResponseContext:
        tags = [*search.tags, Rating.safe.value] if search.safe_only else list(search.tags)
        params: dict[str, Any] = {
            "q": ",".join(tags) or "*",  # NSFW + no tags → "*" (everything)
            "sf": sort.value,
            "sd": "desc",
            "filter_id": self._FILTER_EVERYTHING,
            "per_page": 1,
        }
        if self._api_key:
            params["key"] = self._api_key
        return session.get(self._API, params=params)
