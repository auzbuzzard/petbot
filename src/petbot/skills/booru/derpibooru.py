"""Derpibooru provider (My Little Pony imageboard), API v1.

Tags are comma-separated and may contain spaces within a tag (the site's own
convention; we don't coerce). Rating is a *tag* on Derpibooru, derived from the
image's tag names on the way out. The "everything" filter is always used so the
``safe`` system tag is the only content gate. Errors come back as a 400
``{"error": "..."}``.
"""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field

from petbot.skills.booru import tags
from petbot.skills.booru.base import BooruProvider
from petbot.skills.booru.types import Post, SearchRequest

_NAME = "Derpibooru"
_ROOT = "https://derpibooru.org/"
_ENDPOINT = "https://derpibooru.org/api/v1/json/search/images"
_ICON = "https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg"
_FILTER_EVERYTHING = "56027"  # show all ratings; the `safe` tag is the only gate
_MAX_PER_PAGE = 50


class Sort(tags.Sort):
    random = "random"
    score = "score"
    wilson = "wilson_score"
    relevance = "relevance"
    newest = "created_at"
    first_seen = "first_seen_at"
    updated = "updated_at"
    comments = "comment_count"
    tag_count = "tag_count"
    favorites = "faves"
    width = "width"
    height = "height"
    aspect_ratio = "aspect_ratio"
    duration = "duration"


class Rating(tags.Rating):
    safe = "safe"
    suggestive = "suggestive"
    questionable = "questionable"
    explicit = "explicit"
    semi_grimdark = "semi-grimdark"
    grimdark = "grimdark"
    grotesque = "grotesque"


class FileType(tags.FileType):
    png = "png"
    jpeg = "jpeg"
    gif = "gif"
    svg = "svg"
    webm = "webm"
    mp4 = "mp4"


_COLOR = {
    Rating.safe: 0x00FF00,
    Rating.suggestive: 0x0000FF,
    Rating.questionable: 0xFFFF00,
    Rating.explicit: 0xFF0000,
    Rating.semi_grimdark: 0x80008B,
    Rating.grimdark: 0x000000,
    Rating.grotesque: 0x8B0000,
}
# Most severe first: the worst rating tag present decides colour/safety.
_SEVERITY = (
    Rating.explicit,
    Rating.grimdark,
    Rating.grotesque,
    Rating.semi_grimdark,
    Rating.questionable,
    Rating.suggestive,
    Rating.safe,
)


def _rating(image_tags: list[str]) -> Rating:
    names = {tag.lower() for tag in image_tags}
    return next((r for r in _SEVERITY if r.value in names), Rating.safe)


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


class _Response(BaseModel):
    total: int = 0
    images: list[_Image] = Field(default_factory=list)


class _Error(BaseModel):
    error: str | None = None


class DerpibooruProvider(BooruProvider):
    name: str = _NAME
    site_name: str = _NAME
    Sort: type[tags.Sort] = Sort
    Rating: type[tags.Rating] = Rating
    FileType: type[tags.FileType] = FileType

    def __init__(self, *, api_key: str | None = None):
        self._api_key = api_key

    def parse_tags(self, raw: str) -> tuple[str, ...]:
        # Derpibooru separates tags by commas; spaces are allowed within a tag.
        return tuple(t.strip() for t in raw.split(",") if t.strip())

    def build_request(self, client: httpx.AsyncClient, search: SearchRequest) -> httpx.Request:
        terms = [*search.tags, *self._q_tags(search)]
        params: dict[str, str | int] = {
            "q": ",".join(terms) or "*",
            "sf": (search.sort or Sort.random).value,
            "sd": "desc" if search.descending else "asc",
            "per_page": min(max(search.limit, 1), _MAX_PER_PAGE),
            "page": search.page,
            "filter_id": _FILTER_EVERYTHING,
        }
        if self._api_key:
            params["key"] = self._api_key
        return client.build_request("GET", _ENDPOINT, params=params)

    def parse(self, body: object) -> Post | None:
        decoded = _Response.model_validate(body)
        if not decoded.images:
            return None
        img = decoded.images[0]
        url = img.view_url or img.representations.large
        if not url:
            return None
        if url.startswith("//"):  # `representations` come back protocol-relative
            url = f"https:{url}"
        rating = _rating(img.tags)
        return Post(
            post_id=img.id,
            image_url=url,
            color=_COLOR.get(rating, 0xFFFF00),
            is_safe=rating is Rating.safe,
            score=img.score,
            favorites=img.faves,
            file_ext=img.format,
            page_url=f"{_ROOT}{img.id}",
            site_name=_NAME,
            site_root=_ROOT,
            site_icon_url=_ICON,
            total=decoded.total,
        )

    def error(self, body: object) -> str | None:
        return _Error.model_validate(body).error

    def _q_tags(self, s: SearchRequest) -> list[str]:
        out: list[str] = []
        if s.safe_only:
            out.append(Rating.safe.value)
        elif s.rating is not None:
            out.append(s.rating.value)
        if s.file_type is not None:
            out.append(f"format:{s.file_type.value}")
        out += tags.dotted_filter("score", s.score)
        out += tags.dotted_filter("faves", s.favorites)
        return out
