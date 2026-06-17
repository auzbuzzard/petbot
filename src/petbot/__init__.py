"""PetBot: a Discord bot — an edge that dispatches to skill workers."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    #: Single authoritative version — declared once in ``pyproject.toml`` and read
    #: back from the installed package metadata, never duplicated as a literal.
    __version__ = version("petbot")
except PackageNotFoundError:  # pragma: no cover - only when run from a non-install
    __version__ = "0+unknown"
