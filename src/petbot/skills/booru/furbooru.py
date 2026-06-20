"""Furbooru (furry imageboard) — a Philomena instance, like Derpibooru.

All engine behaviour lives in :mod:`philomena`; this module only declares
Furbooru's rating taxonomy (safe/suggestive/questionable/explicit — no MLP
grimdark tiers) and wires the :class:`~philomena.Site`.
"""

from __future__ import annotations

from petbot.skills.booru import philomena, tags

Sort = philomena.Sort
FileType = philomena.FileType


class Rating(tags.Rating):
    safe = "safe"
    suggestive = "suggestive"
    questionable = "questionable"
    explicit = "explicit"


_SEVERITY = (Rating.explicit, Rating.questionable, Rating.suggestive, Rating.safe)

_COLOR: dict[tags.Rating, int] = {
    Rating.safe: 0x00FF00,
    Rating.suggestive: 0x0000FF,
    Rating.questionable: 0xFFFF00,
    Rating.explicit: 0xFF0000,
}

SITE = philomena.Site(
    name="Furbooru",
    root="https://furbooru.org/",
    endpoint="https://furbooru.org/api/v1/json/search/images",
    icon="https://furbooru.org/favicon.ico",
    filter_everything="2",  # system "Everything" filter; safe tag is the only gate
    rating=Rating,
    severity=_SEVERITY,
    colors=_COLOR,
)


def FurbooruProvider(*, api_key: str | None = None) -> philomena.PhilomenaProvider:
    """Build a Furbooru provider."""
    return philomena.PhilomenaProvider(SITE, api_key=api_key)
