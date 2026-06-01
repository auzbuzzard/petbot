"""Neutral value objects exchanged inside the booru core.

``SearchRequest`` is the intent flowing in; ``Post`` is the normalized result
flowing out. Both are frozen dataclasses with no site vocabulary: a ``Post``
carries an already-resolved accent ``color`` and an ``is_safe`` flag, never a
site-specific rating string. Providers map their wire models onto these.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """A booru search as the skill understands it.

    ``safe_only`` is the one-way safety floor: a SFW channel sets it ``True`` and
    the provider restricts results to the safe rating; a NSFW channel sets it
    ``False`` and no rating filter is applied at all.
    """

    tags: tuple[str, ...]
    safe_only: bool = True


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


def parse_tags(text: str) -> list[str]:
    """Split a comma-separated tag string into clean, non-empty tags."""
    return [tag.strip() for tag in text.split(",") if tag.strip()]
