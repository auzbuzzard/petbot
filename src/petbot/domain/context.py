"""Neutral request context exchanged across the frontend <-> worker boundary.

:class:`~petbot.domain._model.Frozen` pydantic models — pure data, no platform
nouns and no live ports, so a :class:`SkillContext` serialises cleanly inside a
:class:`~petbot.domain.call.SkillCall`. A frontend maps its native request onto
these on the way in; a worker runs a skill against them with no platform
knowledge. Live ports (voice) never ride here — the worker that hosts a
port-requiring skill injects the port itself (see :mod:`petbot.domain.ports`).
"""

from __future__ import annotations

from enum import StrEnum

from petbot.domain._model import Frozen


class Platform(StrEnum):
    """The frontend a request originated from.

    Skills must never branch on this — they read :class:`SkillContext` flags or
    declare a :class:`~petbot.domain.capability.Capability` requirement instead.
    """

    DISCORD = "discord"


class User(Frozen):
    """The invoking user, platform-qualified. ``id`` stays ``str`` for neutrality."""

    platform: Platform
    id: str
    display_name: str


class SkillContext(Frozen):
    """Everything a skill needs about a request, with no platform nouns.

    ``allows_explicit`` and ``style_results`` are *runtime* flags (the booru skills
    raise their rating floor on an NSFW channel; the dispatch boundary styles a
    result for a frontend that has no LLM) — distinct from a hard
    :class:`~petbot.domain.capability.Capability`, which gates whether a skill is
    hosted at all.
    """

    platform: Platform
    user: User
    #: Neutral key identifying the conversation, for grouping its history and
    #: resolving per-conversation worker state (e.g. a music queue + voice port).
    conversation_id: str
    allows_explicit: bool = False
    #: The originating frontend has no LLM to voice the result itself (a slash
    #: command), so the worker applies the persona style on the way out. The
    #: ``@mention`` path leaves this ``False`` — the chat agent voices its own
    #: output, and a nested chat tool-call inherits that ``False``.
    style_results: bool = False
