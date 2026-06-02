"""Neutral value objects exchanged inside the booru core.

``SearchRequest`` is the intent flowing in; ``Post`` is the normalized result
flowing out. ``SearchRequest`` references the abstract :mod:`tags` vocabulary, so
it understands the fundamental search concepts (sort, rating, file type, numeric
ranges, pagination) while each provider keeps its full native value set — the
member's ``.value`` is the wire token, whichever site it came from.
"""

from __future__ import annotations

from dataclasses import dataclass

from petbot.core.capabilities.boorus.tags import FileType, Range, Rating, Sort


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """A booru search as the skill understands it.

    ``safe_only`` is the one-way safety floor: a SFW channel sets it ``True`` and
    the provider restricts results to the safe rating; a NSFW channel sets it
    ``False`` and applies no rating filter (``rating``, if given, still narrows).
    The ``sort``/``rating``/``file_type`` fields hold a *provider* enum member
    (its ``.value`` is the wire token); ``score``/``favorites`` are numeric ranges.
    """

    tags: tuple[str, ...]
    safe_only: bool = True
    sort: Sort | None = None
    rating: Rating | None = None
    file_type: FileType | None = None
    score: Range | None = None
    favorites: Range | None = None
    limit: int = 1
    page: int = 1


@dataclass(frozen=True, slots=True)
class Post:
    """A single normalized search result — exactly what the renderer needs."""

    post_id: int
    image_url: str
    color: int
    is_safe: bool
    score: int
    favorites: int
    file_ext: str
    page_url: str
    site_name: str
    site_root: str
    site_icon_url: str
    total: int | None = None  # match count when the API reports it (Derpibooru)
