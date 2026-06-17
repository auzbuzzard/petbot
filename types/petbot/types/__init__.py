"""PetBot typed skill surface: per-skill ``*Args`` models and the ``Skills`` client.

The cross-package types the edge imports *without* pulling in any skill's runtime
dependencies. See :mod:`petbot.types.args` and :mod:`petbot.types.client`.
"""

from __future__ import annotations

from petbot.types.args import BooruArgs, ChatArgs, MathArgs, MusicAction, MusicArgs
from petbot.types.client import Skills

__all__ = [
    "BooruArgs",
    "ChatArgs",
    "MathArgs",
    "MusicAction",
    "MusicArgs",
    "Skills",
]
