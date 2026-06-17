"""Neutral request context and the dispatch envelope.

Immutable pydantic models — pure, serialisable data: no platform nouns and no
live objects. They cross process boundaries, so they carry only data; a
capability like voice is a *port* injected by the worker that needs it, never a
field here.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from petbot_domain._model import Frozen


class Platform(StrEnum):
    """The frontend a request originated from.

    Skills must never branch on this — they read :class:`SkillContext` flags or
    declare :class:`~petbot_domain.capability.Capability` requirements instead.
    """

    DISCORD = "discord"


class User(Frozen):
    """The invoking user, platform-qualified. ``id`` stays ``str`` for neutrality."""

    platform: Platform
    id: str
    display_name: str


class SkillContext(Frozen):
    """Everything a skill needs about a request, with no platform nouns.

    ``allows_explicit`` is a *runtime* flag (the booru skills raise their rating
    floor on an NSFW channel) — distinct from a hard
    :class:`~petbot_domain.capability.Capability`, which gates whether a skill is
    offered at all.
    """

    platform: Platform
    user: User
    #: Neutral key identifying the conversation, for grouping its history.
    conversation_id: str
    allows_explicit: bool = False
    max_text_length: int = 2000


class DispatchRequest(Frozen):
    """A unit of work a frontend hands to compute over a ``DispatchPort``."""

    skill: str
    args: dict[str, Any]
    context: SkillContext
