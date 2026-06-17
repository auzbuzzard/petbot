"""Declarative skill metadata, decoupled from the implementation.

A :class:`SkillSpec` is the only thing a frontend needs to register a command,
offer an LLM tool, or capability-filter — *without* importing the skill or its
dependencies. Workers emit a manifest of specs; the edge consumes it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from petbot_domain.capability import Capability
from petbot_domain.skill import Skill


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """The data projection of a :class:`~petbot_domain.skill.Skill`."""

    name: str
    description: str
    input_schema: Mapping[str, Any]
    requires: frozenset[Capability] = frozenset()

    @classmethod
    def of(cls, skill: Skill) -> SkillSpec:
        """Derive a spec from a live skill (the single source of truth)."""
        return cls(
            name=skill.name,
            description=skill.description,
            input_schema=skill.input_schema,
            requires=skill.requires,
        )
