"""PetBot typed skill surface: per-skill ``*Args`` models and the ``Skills`` client.

The cross-package types the edge imports *without* pulling in any skill's runtime
dependencies. See :mod:`petbot.types.args` and :mod:`petbot.types.client`.
"""

from __future__ import annotations

from petbot.types.args import BooruArgs, ChatArgs, MathArgs, MusicAction, MusicArgs
from petbot.types.client import Skills
from petbot.types.manifest import COMMANDS, CommandSpec
from petbot.types.pipeline import command_handler, dispatch_command

__all__ = [
    "COMMANDS",
    "BooruArgs",
    "ChatArgs",
    "CommandSpec",
    "MathArgs",
    "MusicAction",
    "MusicArgs",
    "Skills",
    "command_handler",
    "dispatch_command",
]
