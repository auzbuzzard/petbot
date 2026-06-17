"""Serialise skill specs to/from a manifest — the data an edge consumes.

The edge loads this (JSON) to register commands and offer LLM tools without
importing any skill or its dependencies.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from petbot_domain import Capability, SkillSpec


def _to_dict(spec: SkillSpec) -> dict[str, object]:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": dict(spec.input_schema),
        # Sorted list of capability values — stable, JSON-friendly.
        "requires": sorted(cap.value for cap in spec.requires),
    }


def _from_dict(data: dict[str, object]) -> SkillSpec:
    requires = data.get("requires") or []
    if not isinstance(requires, list):
        raise ValueError("manifest 'requires' must be a list")
    schema = data["input_schema"]
    if not isinstance(schema, dict):
        raise ValueError("manifest 'input_schema' must be an object")
    return SkillSpec(
        name=str(data["name"]),
        description=str(data["description"]),
        input_schema=schema,
        requires=frozenset(Capability(str(cap)) for cap in requires),
    )


def to_manifest(specs: Iterable[SkillSpec]) -> list[dict[str, object]]:
    """Project specs into JSON-serialisable dicts."""
    return [_to_dict(spec) for spec in specs]


def from_manifest(data: Iterable[dict[str, object]]) -> list[SkillSpec]:
    """Rebuild specs from manifest dicts."""
    return [_from_dict(item) for item in data]


def dumps(specs: Iterable[SkillSpec]) -> str:
    """Serialise specs to a manifest JSON string."""
    return json.dumps(to_manifest(specs), indent=2, sort_keys=True)


def loads(text: str) -> list[SkillSpec]:
    """Parse a manifest JSON string back into specs."""
    return from_manifest(json.loads(text))
