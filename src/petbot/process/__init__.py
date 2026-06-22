"""The process core: PetBot's ``input -> process -> output`` brain.

The first-class layer. :class:`ChatProcess` is the conversational LLM process (the
headline); :class:`CommandProcess` runs a resolved slash command; :class:`RouterProcess`
picks between them by input type. :class:`Stylist` / :class:`PassthroughStyle` are the
persona voice (a ``StylePort``). A compute service composes these with a
:class:`~petbot.platform.registry.ToolRegistry`; the tools live in :mod:`petbot.skills`.
"""

from __future__ import annotations

from petbot.process.chat import ChatProcess
from petbot.process.command import CommandProcess
from petbot.process.router import RouterProcess
from petbot.process.settings import ChatSettings
from petbot.process.voice import PassthroughStyle, Stylist

__all__ = [
    "ChatProcess",
    "ChatSettings",
    "CommandProcess",
    "PassthroughStyle",
    "RouterProcess",
    "Stylist",
]
