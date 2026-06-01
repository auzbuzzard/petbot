"""The injected HTTP seam.

These structural :class:`~typing.Protocol` types are the *only* thing the booru
core knows about HTTP. The application injects a real ``aiohttp.ClientSession``;
tests inject a fake — both satisfy these protocols without the core importing
aiohttp for anything but ``BasicAuth`` (dependency inversion).

A provider's ``request`` returns the ``session.get(...)`` context manager as-is;
the engine enters it and reads the body. We deliberately never call
``raise_for_status`` — error *bodies* carry the message we want to surface, so we
read the body on every status (see :mod:`petbot.core.capabilities.boorus.engine`).
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Protocol


class HttpResponse(Protocol):
    """The slice of an HTTP response the engine reads."""

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
    """The slice of :class:`aiohttp.ClientSession` the providers depend on."""

    def get(
        self,
        url: str,
        *,
        params: Any = ...,
        headers: Any = ...,
        auth: Any = ...,
    ) -> HttpResponseContext: ...
