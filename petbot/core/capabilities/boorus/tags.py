"""Abstract search vocabulary shared by every booru provider.

A booru search is expressed with *system tags* — enumerated controls like sort
order, rating, and file type — plus numeric ranges (score, favourites). Each site
has its own wire spelling for these, but the *concepts* are shared.

`SystemTag` is the abstract base for an enumerated vocabulary: providers subclass
`Sort`/`Rating`/`FileType` with their **full native** value set, and the member's
`.value` is the on-the-wire token. The neutral :class:`SearchRequest` references
the abstract bases, so the engine stays generic while each provider keeps 100% of
its vocabulary. ``Range`` models a numeric bound; the syntax helpers turn it into
each site's dialect (``score:>=100`` on e621, ``score.gte:100`` on Derpibooru).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SystemTag(StrEnum):
    """Abstract base for a site's enumerated search vocabulary.

    The member ``value`` is the exact token sent to the API. Concrete providers
    subclass the markers below; the empty bases carry no members so they remain
    subclassable (Python forbids extending an enum that already has members).
    """


class Sort(SystemTag):
    """How results are ordered (e621 ``order:`` / Derpibooru ``sf``)."""


class Rating(SystemTag):
    """Content rating (e621 ``rating:`` / a Derpibooru rating tag)."""


class FileType(SystemTag):
    """File format (e621 ``type:`` / Derpibooru ``format:``)."""


@dataclass(frozen=True, slots=True)
class Range:
    """A numeric bound. Each side is independent and may be inclusive or exclusive:
    ``at_least`` (``>=``) / ``greater_than`` (``>``) and ``at_most`` (``<=``) /
    ``less_than`` (``<``). All optional; an empty range serializes to nothing."""

    at_least: int | None = None
    greater_than: int | None = None
    at_most: int | None = None
    less_than: int | None = None

    def __bool__(self) -> bool:
        return any(
            v is not None for v in (self.at_least, self.greater_than, self.at_most, self.less_than)
        )


def operator_range(field: str, r: Range | None) -> list[str]:
    """e621 operator dialect: ``score:>=100``, ``score:>100``, ``score:<=200``."""
    if not r:
        return []
    out: list[str] = []
    if r.at_least is not None:
        out.append(f"{field}:>={r.at_least}")
    if r.greater_than is not None:
        out.append(f"{field}:>{r.greater_than}")
    if r.at_most is not None:
        out.append(f"{field}:<={r.at_most}")
    if r.less_than is not None:
        out.append(f"{field}:<{r.less_than}")
    return out


def dotted_range(field: str, r: Range | None) -> list[str]:
    """Derpibooru qualifier dialect: ``score.gte:100``, ``score.gt:100``, ``score.lte:200``."""
    if not r:
        return []
    out: list[str] = []
    if r.at_least is not None:
        out.append(f"{field}.gte:{r.at_least}")
    if r.greater_than is not None:
        out.append(f"{field}.gt:{r.greater_than}")
    if r.at_most is not None:
        out.append(f"{field}.lte:{r.at_most}")
    if r.less_than is not None:
        out.append(f"{field}.lt:{r.less_than}")
    return out
