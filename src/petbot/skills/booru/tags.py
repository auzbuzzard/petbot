"""Abstract search vocabulary shared by every booru provider.

A booru search is expressed with *system tags* — enumerated controls like sort
order, rating, and file type — plus numeric ranges (score, favourites). Each site
has its own wire spelling for these, but the *concepts* are shared.

`SystemTag` is the abstract base for an enumerated vocabulary: providers subclass
`Sort`/`Rating`/`FileType` with their **full native** value set, and the member's
`.value` is the on-the-wire token. The neutral :class:`SearchRequest` references
the abstract bases, so the engine stays generic while each provider keeps 100% of
its vocabulary.
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
class NumericFilter:
    """A numeric constraint on a field (score, favourites, …).

    A "between" is just ``at_least`` + ``at_most``. All sides optional.
    """

    eq: int | None = None
    ne: int | None = None
    at_least: int | None = None
    greater_than: int | None = None
    at_most: int | None = None
    less_than: int | None = None

    def __bool__(self) -> bool:
        return any(
            v is not None
            for v in (
                self.eq,
                self.ne,
                self.at_least,
                self.greater_than,
                self.at_most,
                self.less_than,
            )
        )


def operator_filter(field: str, f: NumericFilter | None) -> list[str]:
    if not f:
        return []
    out: list[str] = []
    if f.eq is not None:
        out.append(f"{field}:{f.eq}")
    if f.ne is not None:
        out.append(f"-{field}:{f.ne}")
    if f.at_least is not None:
        out.append(f"{field}:>={f.at_least}")
    if f.greater_than is not None:
        out.append(f"{field}:>{f.greater_than}")
    if f.at_most is not None:
        out.append(f"{field}:<={f.at_most}")
    if f.less_than is not None:
        out.append(f"{field}:<{f.less_than}")
    return out


def dotted_filter(field: str, f: NumericFilter | None) -> list[str]:
    if not f:
        return []
    out: list[str] = []
    if f.eq is not None:
        out.append(f"{field}:{f.eq}")
    if f.ne is not None:
        out.append(f"-{field}:{f.ne}")
    if f.at_least is not None:
        out.append(f"{field}.gte:{f.at_least}")
    if f.greater_than is not None:
        out.append(f"{field}.gt:{f.greater_than}")
    if f.at_most is not None:
        out.append(f"{field}.lte:{f.at_most}")
    if f.less_than is not None:
        out.append(f"{field}.lt:{f.less_than}")
    return out
