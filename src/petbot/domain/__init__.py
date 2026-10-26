"""PetBot Shared Kernel: neutral domain models and port interfaces.

Frontends and skills both depend on this; neither depends on the other. See
``docs/adr/0006-gateway-edge-microservice-skills.md``.
"""

from __future__ import annotations

from petbot.domain._model import Frozen
from petbot.domain.capability import Capability
from petbot.domain.context import Platform, SkillContext, User
from petbot.domain.errors import (
    EmptyResult,
    InvalidInput,
    SkillError,
    UpstreamUnavailable,
)
from petbot.domain.input import (
    CommandInput,
    History,
    Input,
    Recalled,
    Role,
    TextInput,
    Turn,
    Unrecalled,
)
from petbot.domain.ports import (
    Notifier,
    StylePort,
    TrackFinishedCallback,
    VoicePort,
    VoiceProvider,
)
from petbot.domain.process import Process
from petbot.domain.result import EmbedSpec, SkillResult, ToolCall
from petbot.domain.skill import Skill

__all__ = [
    "Capability",
    "CommandInput",
    "EmbedSpec",
    "EmptyResult",
    "Frozen",
    "History",
    "Input",
    "InvalidInput",
    "Notifier",
    "Platform",
    "Process",
    "Recalled",
    "Role",
    "Skill",
    "SkillContext",
    "SkillError",
    "SkillResult",
    "StylePort",
    "TextInput",
    "ToolCall",
    "TrackFinishedCallback",
    "Turn",
    "Unrecalled",
    "UpstreamUnavailable",
    "User",
    "VoicePort",
    "VoiceProvider",
]
