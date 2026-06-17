"""The provider contract the generic engine talks to.

A provider owns everything site-specific: its full native ``Sort``/``Rating``/
``FileType`` vocabularies, how a raw tag string is split (each site has its own
convention), how a :class:`SearchRequest` is serialized into an HTTP request, and
how a response body becomes a :class:`Post` or an error message. The engine only
ever calls ``build_request``/``parse``/``error`` and never inspects vocabulary.
"""

from __future__ import annotations

from typing import Protocol

import httpx

from petbot.skills.booru import tags
from petbot.skills.booru.types import Post, SearchRequest


class BooruProvider(Protocol):
    """Everything the engine needs from a site, and nothing site-specific leaks."""

    name: str
    site_name: str
    #: The provider's full native vocabularies (subclasses of the abstract bases).
    Sort: type[tags.Sort]
    Rating: type[tags.Rating]
    FileType: type[tags.FileType]

    def parse_tags(self, raw: str) -> tuple[str, ...]:
        """Split a raw user tag string per this site's convention."""
        ...

    def build_request(self, client: httpx.AsyncClient, search: SearchRequest) -> httpx.Request:
        """Serialize a search into a ready-to-send request (incl. headers/auth)."""
        ...

    def parse(self, body: object) -> Post | None:
        """Turn a decoded success body into the first result, or ``None``."""
        ...

    def error(self, body: object) -> str | None:
        """Return the site's failure message if ``body`` is an error, else ``None``."""
        ...
