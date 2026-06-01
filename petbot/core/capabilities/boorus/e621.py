"""e621 provider (furry imageboard), modern ``/posts.json`` schema.

A descriptive User-Agent is mandatory (browser-spoofing UAs are blocked), and
optional ``username``/``api_key`` HTTP basic auth raises rate limits. The safety
floor is the ``rating:s`` search tag: a SFW channel adds it, a NSFW channel adds
no rating tag at all. An error body is ``{"success": false, "message": "..."}``
(e.g. the 422 returned when an anonymous search exceeds 40 tags).
"""

from __future__ import annotations

from enum import StrEnum

import aiohttp
from pydantic import BaseModel, Field

from petbot.core.capabilities.boorus.base import BooruResponse, ErrorResponse
from petbot.core.capabilities.boorus.http import HttpResponseContext, HttpSession
from petbot.core.capabilities.boorus.types import Post, SearchRequest


class Sort(StrEnum):
    random = "random"
    score = "score"
    favcount = "favcount"
    newest = "id"
    comments = "comment_count"


class Rating(StrEnum):
    safe = "s"
    questionable = "q"
    explicit = "e"


_COLOR = {
    Rating.safe: 0x00FF00,
    Rating.questionable: 0xFFFF00,
    Rating.explicit: 0xFF0000,
}
_NAME = "e621"
_ROOT = "https://e621.net/"
_ICON = "https://e621.net/favicon-32x32.png"


class _File(BaseModel):
    url: str | None = None
    ext: str = ""


class _Sample(BaseModel):
    url: str | None = None


class _Score(BaseModel):
    total: int = 0


class _Post(BaseModel):
    id: int
    file: _File = Field(default_factory=_File)
    sample: _Sample = Field(default_factory=_Sample)
    score: _Score = Field(default_factory=_Score)
    fav_count: int = 0
    rating: Rating = Rating.safe  # "s"/"q"/"e" coerced into the enum by pydantic


class Response(BooruResponse):
    posts: list[_Post] = Field(default_factory=list)

    def to_post(self) -> Post | None:
        if not self.posts:
            return None
        post = self.posts[0]
        url = post.sample.url or post.file.url
        if not url:  # blocked posts have null urls
            return None
        return Post(
            post_id=post.id,
            image_url=url,
            color=_COLOR[post.rating],
            is_safe=post.rating is Rating.safe,
            score=post.score.total,
            favorites=post.fav_count,
            file_ext=post.file.ext,
            page_url=f"{_ROOT}posts/{post.id}",
            site_name=_NAME,
            site_root=_ROOT,
            site_icon_url=_ICON,
        )


class Error(ErrorResponse):
    success: bool = True
    message: str | None = None

    def reason(self) -> str | None:
        return self.message if self.success is False else None


class E621Provider:
    name: str = _NAME
    response_model: type[BooruResponse] = Response
    error_model: type[ErrorResponse] = Error

    def __init__(
        self,
        *,
        user_agent: str,
        username: str | None = None,
        api_key: str | None = None,
    ):
        self._user_agent = user_agent
        self._username = username
        self._api_key = api_key

    def request(
        self,
        session: HttpSession,
        search: SearchRequest,
        *,
        sort: Sort = Sort.random,
    ) -> HttpResponseContext:
        tags = [*search.tags, f"order:{sort.value}"]
        if search.safe_only:
            tags.append(f"rating:{Rating.safe.value}")  # NSFW: no rating tag → all ratings
        auth = (
            aiohttp.BasicAuth(self._username, self._api_key)
            if self._username and self._api_key
            else None
        )
        return session.get(
            _ROOT + "posts.json",
            params={"tags": " ".join(tags), "limit": 1},
            headers={"User-Agent": self._user_agent},  # mandatory
            auth=auth,
        )
