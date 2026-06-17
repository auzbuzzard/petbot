"""The registry indexes by name and filters by capability requirements."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from petbot_domain import Capability, Skill, SkillContext, SkillResult
from petbot_platform import SkillNotFoundError, SkillRegistry


class _Skill(Skill):
    def __init__(self, name: str, requires: frozenset[Capability] = frozenset()) -> None:
        self.name = name
        self.description = "x"
        self.input_schema = {"type": "object"}
        self.requires = requires

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        return SkillResult.message(self.name)


def test_get_and_missing() -> None:
    reg = SkillRegistry([_Skill("a")])
    assert reg.get("a").name == "a"
    with pytest.raises(SkillNotFoundError):
        reg.get("nope")


def test_duplicate_name_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        SkillRegistry([_Skill("a"), _Skill("a")])


def test_available_for_filters_by_requires() -> None:
    reg = SkillRegistry([_Skill("plain"), _Skill("voice", frozenset({Capability.VOICE}))])
    assert {s.name for s in reg.available_for(frozenset())} == {"plain"}
    offered = reg.available_for(frozenset({Capability.VOICE}))
    assert {s.name for s in offered} == {"plain", "voice"}


def test_specs_projection_carries_requires() -> None:
    reg = SkillRegistry([_Skill("a", frozenset({Capability.VOICE}))])
    spec = reg.specs()[0]
    assert spec.name == "a"
    assert spec.requires == frozenset({Capability.VOICE})
