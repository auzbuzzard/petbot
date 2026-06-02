"""e621 provider (furry imageboard), modern ``/posts.json`` schema.

Tags are space-separated and use underscores within a tag (the user follows the
site's own convention; we don't coerce). A descriptive User-Agent is mandatory,
and optional ``username``/``api_key`` basic auth (sent as an ``Authorization``
header so the engine stays generic) raises rate limits. The safety floor is the
``rating:s`` system tag. Errors come back as ``{"success": false, "message": …}``
(e.g. the 422 when an anonymous search exceeds 40 tags).
"""

from __future__ import annotations

import base64

import httpx
from pydantic import BaseModel, Field

from petbot.core.capabilities.boorus import tags
from petbot.core.capabilities.boorus.types import Post, SearchRequest

_NAME = "e621"
_ROOT = "https://e621.net/"
_ENDPOINT = "https://e621.net/posts.json"
_ICON = "https://e621.net/apple-touch-icon.png"
_MAX_LIMIT = 320  # e621 rejects larger page sizes


class Sort(tags.Sort):
    random = "random"
    score = "score"
    score_asc = "score_asc"
    favorites = "favcount"
    favorites_asc = "favcount_asc"
    comments = "comment_count"
    comments_asc = "comment_count_asc"
    comment_bumped = "comment_bumped"
    newest = "created"
    oldest = "created_asc"
    updated = "updated"
    updated_asc = "updated_asc"
    id_oldest = "id"
    id_newest = "id_desc"
    mpixels = "mpixels"
    mpixels_asc = "mpixels_asc"
    filesize = "filesize"
    filesize_asc = "filesize_asc"
    duration = "duration"
    duration_asc = "duration_asc"
    landscape = "landscape"
    portrait = "portrait"
    tagcount = "tagcount"
    hot = "hot"


class Rating(tags.Rating):
    safe = "s"
    questionable = "q"
    explicit = "e"


class FileType(tags.FileType):
    jpg = "jpg"
    png = "png"
    gif = "gif"
    webm = "webm"
    swf = "swf"


_COLOR = {Rating.safe: 0x00FF00, Rating.questionable: 0xFFFF00, Rating.explicit: 0xFF0000}


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


class _Response(BaseModel):
    posts: list[_Post] = Field(default_factory=list)


class _Error(BaseModel):
    success: bool = True
    message: str | None = None


class E621Provider:
    name: str = _NAME
    site_name: str = _NAME
    Sort: type[tags.Sort] = Sort
    Rating: type[tags.Rating] = Rating
    FileType: type[tags.FileType] = FileType

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

    def parse_tags(self, raw: str) -> tuple[str, ...]:
        # e621 separates tags by spaces; underscores live *within* a tag.
        return tuple(raw.split())

    def build_request(self, client: httpx.AsyncClient, search: SearchRequest) -> httpx.Request:
        words = [*search.tags, *self._system_tags(search)]
        return client.build_request(
            "GET",
            _ENDPOINT,
            params={
                "tags": " ".join(words),
                "limit": min(max(search.limit, 1), _MAX_LIMIT),
                "page": search.page,
            },
            headers={"User-Agent": self._user_agent, **self._auth_header()},
        )

    def parse(self, body: object) -> Post | None:
        posts = _Response.model_validate(body).posts
        if not posts:
            return None
        post = posts[0]
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

    def error(self, body: object) -> str | None:
        e = _Error.model_validate(body)
        return e.message if e.success is False else None

    def _system_tags(self, s: SearchRequest) -> list[str]:
        out: list[str] = []
        if s.safe_only:
            out.append(f"rating:{Rating.safe.value}")
        elif s.rating is not None:
            out.append(f"rating:{s.rating.value}")
        if s.sort is not None:
            # e621 encodes direction in the order value (e.g. score vs score_asc),
            # so SearchRequest.descending is not applied here.
            out.append(f"order:{s.sort.value}")
        if s.file_type is not None:
            out.append(f"type:{s.file_type.value}")
        out += tags.operator_filter("score", s.score)
        out += tags.operator_filter("favcount", s.favorites)
        return out

    def _auth_header(self) -> dict[str, str]:
        if self._username and self._api_key:
            token = base64.b64encode(f"{self._username}:{self._api_key}".encode()).decode()
            return {"Authorization": f"Basic {token}"}
        return {}
