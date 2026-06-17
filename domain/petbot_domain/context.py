"""Neutral request context and the dispatch envelope.

Frozen, slotted value objects exchanged across the frontend <-> skill boundary.
None of it mentions a platform: a frontend maps its native request onto these on
the way in, and a worker runs a skill against them with no platform knowledge.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from petbot_domain.ports import VoicePort


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
    #: Neutral session key (the LLM layer keys conversation history off this).
    conversation_id: str
    allows_explicit: bool = False
    max_text_length: int = 2000
    #: Present iff the frontend provides ``Capability.VOICE``; the worker that runs
    #: a voice skill injects a concrete implementation.
    voice: VoicePort | None = None


@dataclass(frozen=True, slots=True)
class DispatchRequest:
    """A unit of work a frontend hands to decoupled compute over a ``DispatchPort``.

    Carries the target skill name, its validated ``args``, and the neutral
    ``SkillContext`` — minus live ports, which never cross a process boundary. A
    port-requiring skill (e.g. music) is served by a worker that reconstructs the
    port locally.
    """

    skill: str
    args: Mapping[str, Any]
    context: SkillContext
