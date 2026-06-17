"""SkillSpec derives faithfully from a Skill, decoupled from its implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from petbot_domain import Capability, SkillContext, SkillResult, SkillSpec
from petbot_domain.skill import Skill


class _FakeSkill(Skill):
    name = "demo"
    description = "A demo skill."
    input_schema: Mapping[str, Any] = {"type": "object", "properties": {"q": {"type": "string"}}}
    requires = frozenset({Capability.VOICE})

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        return SkillResult.message("ok")


def test_spec_of_derives_metadata() -> None:
    spec = SkillSpec.of(_FakeSkill())
    assert spec.name == "demo"
    assert spec.description == "A demo skill."
    assert spec.input_schema == _FakeSkill.input_schema
    assert spec.requires == frozenset({Capability.VOICE})


def test_spec_requires_defaults_empty() -> None:
    class _NoReq(Skill):
        name = "noreq"
        description = "No requirements."
        input_schema: Mapping[str, Any] = {"type": "object"}

        async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
            return SkillResult.message()

    assert SkillSpec.of(_NoReq()).requires == frozenset()


def test_spec_equality_is_by_value() -> None:
    a = SkillSpec("x", "d", {"type": "object"})
    b = SkillSpec("x", "d", {"type": "object"})
    assert a == b
