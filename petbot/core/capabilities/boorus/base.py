"""The provider contract the generic engine talks to.

Each site ships two pydantic models — a success body that knows how to become a
:class:`~petbot.core.capabilities.boorus.types.Post`, and an error body that
knows its own failure message — plus a provider object that names them. The
engine never touches site-specific shapes; it only calls ``to_post`` and
``reason`` through these bases.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from petbot.core.capabilities.boorus.types import Post


class BooruResponse(BaseModel):
    """A decoded *success* body. Subclasses map their JSON onto a ``Post``."""

    def to_post(self) -> Post | None:
        """Return the first result as a neutral ``Post``, or ``None`` if empty."""
        raise NotImplementedError


class ErrorResponse(BaseModel):
    """A decoded *error* body.

    ``reason`` returns the site's message when this body actually represents a
    failure, else ``None`` — so it is safe to validate against any body (pydantic
    ignores the extra success fields and ``reason`` simply returns ``None``).
    """

    def reason(self) -> str | None:
        raise NotImplementedError


class BooruProvider(Protocol):
    """The engine's entire view of a provider: a name and its two models."""

    name: str
    response_model: type[BooruResponse]
    error_model: type[ErrorResponse]
