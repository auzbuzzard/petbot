"""Shared booru building blocks: a generic result holder, an async query base,
and the personality-driven result greeter."""

from __future__ import annotations

import json
import random
from collections.abc import Mapping, Sequence
from functools import lru_cache
from importlib import resources
from types import TracebackType
from typing import Any, Protocol

import aiohttp

_UTTERANCES_RESOURCE = "utterances.json"


class HttpResponse(Protocol):
    """The slice of an HTTP response the providers use."""

    def raise_for_status(self) -> None: ...

    async def json(self, content_type: str | None = ...) -> Any: ...


class HttpResponseContext(Protocol):
    """An async context manager yielding an :class:`HttpResponse`."""

    async def __aenter__(self) -> HttpResponse: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class HttpSession(Protocol):
    """The slice of :class:`aiohttp.ClientSession` the providers depend on.

    Declared as a structural protocol so the application injects a real
    ``aiohttp.ClientSession`` while tests inject a fake — both satisfy it without
    any import back into the core (dependency inversion).
    """

    def get(
        self,
        url: str,
        *,
        params: Any = ...,
        headers: Any = ...,
        auth: Any = ...,
    ) -> HttpResponseContext: ...


class Result:
    """A thin attribute view over a JSON object.

    Lets provider code read ``result.score`` etc. without ceremony. Provider
    subclasses derive richer fields (rating, explicitness) in ``__init__``.
    """

    def __init__(self, data: Mapping[str, Any]):
        for key, value in data.items():
            setattr(self, key, value)


class SearchQuery:
    """Base class for a booru search request.

    The HTTP session is injected (see :class:`HttpSession`), not held as a
    module global, so connections are owned by the application and easily mocked.
    """

    root_url: str = "/"

    def __init__(
        self,
        tags: Sequence[str],
        args: Mapping[str, Any],
        *,
        session: HttpSession,
    ):
        self.tags = list(tags)
        self.args = dict(args)
        self.is_explicit: bool = bool(args.get("explicit", False))
        self._session = session

    def params(self) -> dict[str, Any]:
        """Query-string parameters for the request (overridden per provider)."""
        return {}

    def endpoint(self) -> str:
        """Absolute URL of the search endpoint (overridden per provider)."""
        return self.root_url

    def headers(self) -> dict[str, str]:
        """Extra request headers (e.g. a descriptive User-Agent)."""
        return {}

    def auth(self) -> aiohttp.BasicAuth | None:
        """Optional HTTP basic auth (overridden per provider)."""
        return None

    async def request(self) -> dict[str, Any]:
        """Perform the search and return the decoded JSON body."""
        async with self._session.get(
            self.endpoint(),
            params=self.params(),
            headers=self.headers(),
            auth=self.auth(),
        ) as response:
            response.raise_for_status()
            data: Any = await response.json(content_type=None)
        if not isinstance(data, dict):
            return {"_payload": data}
        return data


@lru_cache(maxsize=1)
def _load_utterances() -> Mapping[str, Any]:
    text = resources.files(__package__).joinpath(_UTTERANCES_RESOURCE).read_text(encoding="utf-8")
    parsed: Mapping[str, Any] = json.loads(text)
    return parsed


def result_greeter(*, has_image: bool, is_explicit: bool, author: str) -> str:
    """Return a randomized, in-character greeting for a search result.

    ``author`` is a plain display name (no Discord objects), keeping this neutral.
    """
    try:
        greeter = _load_utterances()["image_result_greeter"]
        bucket = greeter["success"] if has_image else greeter["no_image"]
        sentences: list[str] = list(bucket["universal"])
        sentences += bucket["explicit"] if is_explicit else bucket["safe"]
        return random.choice(sentences).format(author=author)
    except (OSError, KeyError, ValueError):
        return "I have found this image." if has_image else "I couldn't find anything."
