"""Neutral request context exchanged across the frontend <-> compute boundary.

:class:`~petbot.domain._model.Frozen` pydantic models — pure data, no platform nouns
and no live ports, so a :class:`SkillContext` serialises cleanly across the wire. A
frontend maps its native request onto these on the way in; a compute service runs a
skill against them with no platform knowledge. Live ports (voice) never ride here — the
service that hosts a port-requiring skill injects the port itself (see
:mod:`petbot.domain.ports`).
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

    ``allows_explicit`` is a *runtime* flag (the booru skills raise their rating floor
    on an NSFW channel) — distinct from a hard
    :class:`~petbot.domain.capability.Capability`, which gates whether a skill is hosted
    at all. There is no styling/presentation flag here: which process voices a result is
    decided by the ``Input`` type at dispatch, not carried as request data.
    """

    platform: Platform
    user: User
    #: Neutral key identifying the conversation, for grouping its history and
    #: resolving per-conversation compute state (e.g. a music queue + voice port).
    conversation_id: str
    allows_explicit: bool = False
