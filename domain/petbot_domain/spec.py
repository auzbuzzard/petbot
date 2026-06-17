"""Declarative skill metadata and the manifest an edge reads.

A :class:`SkillSpec` is the data projection of a skill — the only thing an edge
needs to register a command or offer an LLM tool, without importing the skill or
its dependencies. A :class:`Manifest` is the set of them, self-serialising for
delivery to the edge.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from petbot_domain._model import Frozen
from petbot_domain.capability import Capability
from petbot_domain.skill import Skill


class SkillSpec(Frozen):
    """The data projection of a :class:`~petbot_domain.skill.Skill`."""

    name: str
    description: str
    input_schema: dict[str, Any]
    requires: frozenset[Capability] = frozenset()

    @classmethod
    def of(cls, skill: Skill) -> SkillSpec:
        """Derive a spec from a live skill (the single source of truth)."""
        return cls(
            name=skill.name,
            description=skill.description,
            input_schema=dict(skill.input_schema),
            requires=skill.requires,
        )


class Manifest(Frozen):
    """The set of skills an edge may expose."""

    skills: tuple[SkillSpec, ...] = ()

    @classmethod
    def of(cls, skills: Iterable[Skill]) -> Manifest:
        """Build a manifest from live skills."""
        return cls(skills=tuple(SkillSpec.of(skill) for skill in skills))
