"""Philomena imageboard engine (Derpibooru, Furbooru, …), API v1.

Every Philomena instance speaks the same dialect: comma-separated tags (spaces
allowed within a tag), an ``/api/v1/json/search/images`` endpoint taking
``q``/``sf``/``sd``/``per_page``/``filter_id``/``key``, dotted numeric filters
(``score.gte:100``), rating expressed as a *tag* (derived from the image's tags
on the way out), and a ``{"total": ..., "images": [...]}`` body.

Instances differ only in *data* — base URL, the "everything" filter id, and which
ratings the site defines — so a single :class:`PhilomenaProvider` is configured
by a :class:`Site` dataclass rather than subclassed per site.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx
from pydantic import BaseModel, Field

from petbot.skills.booru import tags
from petbot.skills.booru.base import BooruProvider
from petbot.skills.booru.types import Post, SearchRequest


# Sort fields and file formats are baked into the Philomena software itself, so
# they are identical across all instances and defined once here.
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


class FileType(tags.FileType):
    png = "png"
    jpeg = "jpeg"
    gif = "gif"
    svg = "svg"
    webm = "webm"
    mp4 = "mp4"


@dataclass(frozen=True, slots=True)
class Site:
    """Everything that distinguishes one Philomena instance from another.

    ``filter_everything`` is the site's filter that hides nothing, so the
    ``safe`` tag stays the only content gate. ``severity`` is most-severe-first:
    the worst rating tag present on an image decides its colour and safety.
    ``colors`` maps each rating to a Discord embed colour.
    """

    name: str
    root: str
    endpoint: str
    icon: str
    filter_everything: str
    rating: type[tags.Rating]
    severity: tuple[tags.Rating, ...]
    colors: Mapping[tags.Rating, int] = field(default_factory=dict)
    max_per_page: int = 50


# --- Pydantic models for the wire format --------------------------------------


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


# --- Provider -----------------------------------------------------------------


class PhilomenaProvider(BooruProvider):
    """A :class:`BooruProvider` for any Philomena site.

    Behaviour is shared; the :class:`Site` supplies the data that distinguishes
    each instance (URL, filter id, rating vocabulary, colours).
    """

    Sort: type[tags.Sort] = Sort
    FileType: type[tags.FileType] = FileType

    def __init__(self, site: Site, *, api_key: str | None = None) -> None:
        self._site = site
        self._api_key = api_key
        self.name = site.name
        self.site_name = site.name
        self.Rating: type[tags.Rating] = site.rating  # per-site; Sort/FileType are shared

    def parse_tags(self, raw: str) -> tuple[str, ...]:
        # Philomena separates tags by commas; spaces are allowed within a tag.
        return tuple(t.strip() for t in raw.split(",") if t.strip())

    def build_request(self, client: httpx.AsyncClient, search: SearchRequest) -> httpx.Request:
        terms = [*search.tags, *self._q_tags(search)]
        params: dict[str, str | int] = {
            "q": ",".join(terms) or "*",
            "sf": (search.sort or Sort.random).value,
            "sd": "desc" if search.descending else "asc",
            "per_page": min(max(search.limit, 1), self._site.max_per_page),
            "page": search.page,
            "filter_id": self._site.filter_everything,
        }
        if self._api_key:
            params["key"] = self._api_key
        return client.build_request("GET", self._site.endpoint, params=params)

    def parse(self, body: object) -> Post | None:
        decoded = _Response.model_validate(body)
        if not decoded.images:
            return None
        img = decoded.images[0]
        url = img.view_url or img.representations.large
        if not url:
            return None
        if url.startswith("//"):  # representations come back protocol-relative
            url = f"https:{url}"
        rating = self._infer_rating(img.tags)
        return Post(
            post_id=img.id,
            image_url=url,
            color=self._site.colors.get(rating, 0xFFFF00),
            is_safe=rating.value == "safe",  # "safe" is the safe tag on every Philomena instance
            score=img.score,
            favorites=img.faves,
            file_ext=img.format,
            page_url=f"{self._site.root}{img.id}",
            site_name=self._site.name,
            site_root=self._site.root,
            site_icon_url=self._site.icon,
            total=decoded.total,
        )

    def error(self, body: object) -> str | None:
        return _Error.model_validate(body).error

    def _infer_rating(self, image_tags: list[str]) -> tags.Rating:
        names = {t.lower() for t in image_tags}
        # severity is most-severe-first; the last entry is always the safe fallback
        return next(
            (r for r in self._site.severity if r.value in names),
            self._site.severity[-1],
        )

    def _q_tags(self, s: SearchRequest) -> list[str]:
        out: list[str] = []
        if s.safe_only:
            out.append("safe")  # "safe" is the Philomena safe-rating tag on every instance
        elif s.rating is not None:
            out.append(s.rating.value)
        if s.file_type is not None:
            out.append(f"format:{s.file_type.value}")
        out += tags.dotted_filter("score", s.score)
        out += tags.dotted_filter("faves", s.favorites)
        return out
