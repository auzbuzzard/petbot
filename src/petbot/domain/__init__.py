"""PetBot Shared Kernel: neutral domain models and port interfaces.

Frozen pydantic models for the data, an ABC for the typed ``Skill`` contract,
Protocols for the ports and the transport. Frontends and skills both depend on
this; neither depends on the other. See
``docs/adr/0006-gateway-edge-microservice-skills.md``.
"""

from __future__ import annotations

from petbot.domain._model import Frozen
from petbot.domain.call import SkillCall, Transport
from petbot.domain.capability import Capability
from petbot.domain.context import Platform, SkillContext, User
from petbot.domain.input import CommandInput, Input, TextInput
from petbot.domain.ports import (
    Notifier,
    StylePort,
    StyleProvider,
    TrackFinishedCallback,
    VoicePort,
    VoiceProvider,
)
from petbot.domain.process import Process
from petbot.domain.result import EmbedSpec, SkillResult
from petbot.domain.skill import Skill

__all__ = [
    "Capability",
    "CommandInput",
    "EmbedSpec",
    "Frozen",
    "Input",
    "Notifier",
    "Platform",
    "Process",
    "Skill",
    "SkillCall",
    "SkillContext",
    "SkillResult",
    "StylePort",
    "StyleProvider",
    "TextInput",
    "TrackFinishedCallback",
    "Transport",
    "User",
    "VoicePort",
    "VoiceProvider",
]
