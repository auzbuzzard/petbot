"""Manifest serialisation round-trips a spec, including its capabilities."""

from __future__ import annotations

from petbot_domain import Capability, SkillSpec
from petbot_platform import dumps, from_manifest, loads, to_manifest


def _spec() -> SkillSpec:
    return SkillSpec(
        name="demo",
        description="d",
        input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
        requires=frozenset({Capability.VOICE, Capability.RICH_EMBEDS}),
    )


def test_json_round_trip_preserves_spec() -> None:
    spec = _spec()
    back = loads(dumps([spec]))
    assert back == [spec]


def test_requires_serialised_as_capability_values() -> None:
    entry = to_manifest([_spec()])[0]
    assert set(entry["requires"]) == {Capability.VOICE.value, Capability.RICH_EMBEDS.value}


def test_from_manifest_defaults_empty_requires() -> None:
    specs = from_manifest([{"name": "n", "description": "d", "input_schema": {}}])
    assert specs[0].requires == frozenset()
