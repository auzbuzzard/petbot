"""SkillSpec derives from a skill; the Manifest self-serialises for the edge."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from petbot_domain import Capability, Manifest, Skill, SkillContext, SkillResult, SkillSpec


class _Skill(Skill):
    name = "demo"
    description = "A demo skill."
    input_schema: Mapping[str, Any] = {"type": "object", "properties": {"q": {"type": "string"}}}
    requires = frozenset({Capability.VOICE})

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        return SkillResult.message("ok")


def test_spec_of_derives_metadata() -> None:
    spec = SkillSpec.of(_Skill())
    assert spec.name == "demo"
    assert spec.requires == frozenset({Capability.VOICE})


def test_manifest_round_trips() -> None:
    manifest = Manifest.of([_Skill()])
    back = Manifest.model_validate_json(manifest.model_dump_json())
    assert back == manifest
    assert back.skills[0].name == "demo"
