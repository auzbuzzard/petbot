"""PetBot Shared Kernel: neutral domain types and port interfaces.

This package depends on nothing. Frontends and skills both depend on it; neither
depends on the other. See ``docs/adr/0006-gateway-edge-microservice-skills.md``.
"""

from __future__ import annotations

from petbot_domain.capability import Capability
from petbot_domain.context import DispatchRequest, Platform, SkillContext, User
from petbot_domain.ports import DispatchPort, TrackFinishedCallback, VoicePort
from petbot_domain.result import EmbedSpec, SkillResult
from petbot_domain.skill import Skill
from petbot_domain.spec import SkillSpec

__all__ = [
    "Capability",
    "DispatchPort",
    "DispatchRequest",
    "EmbedSpec",
    "Platform",
    "Skill",
    "SkillContext",
    "SkillResult",
    "SkillSpec",
    "TrackFinishedCallback",
    "User",
    "VoicePort",
]
