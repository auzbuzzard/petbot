"""Neutral request context and the dispatch envelope.

Frozen, slotted dataclasses — pure data, no platform nouns and no live objects.
A frontend maps its native request onto these; a worker runs a skill against
them. They cross process boundaries, so they carry only serialisable data: a
capability like voice is a *port* injected by the worker that needs it, never a
field here.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Platform(StrEnum):
    """The frontend a request originated from.

    Skills must never branch on this — they read :class:`SkillContext` flags or
    declare :class:`~petbot_domain.capability.Capability` requirements instead.
    """

    DISCORD = "discord"


@dataclass(frozen=True, slots=True)
class User:
    """The invoking user, platform-qualified. ``id`` stays ``str`` for neutrality."""

    platform: Platform
    id: str
    display_name: str


@dataclass(frozen=True, slots=True)
class SkillContext:
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


@dataclass(frozen=True, slots=True)
class DispatchRequest:
    """A unit of work a frontend hands to compute over a ``DispatchPort``.

    Carries only serialisable data — the target skill, its validated ``args``,
    and the neutral ``SkillContext``.
    """

    skill: str
    args: Mapping[str, Any]
    context: SkillContext
