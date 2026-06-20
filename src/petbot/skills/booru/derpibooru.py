"""Derpibooru (My Little Pony imageboard) — a Philomena instance.

All engine behaviour lives in :mod:`philomena`; this module only declares
Derpibooru's rating taxonomy (it keeps the MLP-specific grimdark/grotesque tiers
that Furbooru does not have) and wires the :class:`~philomena.Site`.
"""

from __future__ import annotations

from petbot.skills.booru import philomena, tags

# Re-export the shared Philomena vocabulary so callers can say derpibooru.Sort
# and derpibooru.FileType without knowing about the philomena module.
Sort = philomena.Sort
FileType = philomena.FileType


class Rating(tags.Rating):
    safe = "safe"
    suggestive = "suggestive"
    questionable = "questionable"
    explicit = "explicit"
    semi_grimdark = "semi-grimdark"
    grimdark = "grimdark"
    grotesque = "grotesque"


# Most severe first; the last entry (safe) is the fallback when no rating tag
# is present on an image.
_SEVERITY = (
    Rating.explicit,
    Rating.grimdark,
    Rating.grotesque,
    Rating.semi_grimdark,
    Rating.questionable,
    Rating.suggestive,
    Rating.safe,
)

_COLOR: dict[tags.Rating, int] = {
    Rating.safe: 0x00FF00,
    Rating.suggestive: 0x0000FF,
    Rating.questionable: 0xFFFF00,
    Rating.explicit: 0xFF0000,
    Rating.semi_grimdark: 0x80008B,
    Rating.grimdark: 0x000000,
    Rating.grotesque: 0x8B0000,
}

SITE = philomena.Site(
    name="Derpibooru",
    root="https://derpibooru.org/",
    endpoint="https://derpibooru.org/api/v1/json/search/images",
    icon="https://derpicdn.net/img/2017/10/22/1567638/thumb_small.jpeg",
    filter_everything="56027",  # system "Everything" filter; safe tag is the only gate
    rating=Rating,
    severity=_SEVERITY,
    colors=_COLOR,
)


def DerpibooruProvider(*, api_key: str | None = None) -> philomena.PhilomenaProvider:
    """Build a Derpibooru provider (factory kept for backwards-compat call sites)."""
    return philomena.PhilomenaProvider(SITE, api_key=api_key)
