"""Skill manifest: the spec list an edge reads to register commands and offer LLM
tools without importing any skill. Pydantic serialises the kernel's ``SkillSpec``
dataclasses; no hand-rolled JSON.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, cast

from pydantic import TypeAdapter

from petbot_domain import SkillSpec

_MANIFEST: TypeAdapter[list[SkillSpec]] = TypeAdapter(list[SkillSpec])


def to_manifest(specs: Iterable[SkillSpec]) -> list[dict[str, Any]]:
    """Project specs into JSON-serialisable dicts."""
    return cast(list[dict[str, Any]], _MANIFEST.dump_python(list(specs), mode="json"))


def from_manifest(data: Iterable[dict[str, Any]]) -> list[SkillSpec]:
    """Rebuild specs from manifest dicts."""
    return _MANIFEST.validate_python(list(data))


def dumps(specs: Iterable[SkillSpec]) -> str:
    """Serialise specs to a manifest JSON string."""
    return _MANIFEST.dump_json(list(specs), indent=2).decode()


def loads(text: str | bytes) -> list[SkillSpec]:
    """Parse a manifest JSON string back into specs."""
    return _MANIFEST.validate_json(text)
