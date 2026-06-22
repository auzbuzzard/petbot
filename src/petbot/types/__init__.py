"""PetBot typed surface: per-skill ``*Args`` models and the command catalog.

The cross-package types a frontend imports *without* pulling in any skill's runtime
dependencies. See :mod:`petbot.types.args` and :mod:`petbot.types.catalog`.
"""

from __future__ import annotations

from petbot.types.args import BooruArgs, MathArgs, MusicAction, MusicArgs
from petbot.types.catalog import CATALOG, Command

__all__ = [
    "CATALOG",
    "BooruArgs",
    "Command",
    "MathArgs",
    "MusicAction",
    "MusicArgs",
]
