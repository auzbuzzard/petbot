"""PetBot runtime: skill discovery, registry, manifest, and dispatch adapters."""

from __future__ import annotations

from petbot_platform.dispatch import InProcessDispatch
from petbot_platform.loader import SKILLS_GROUP, build_registry, load_skills
from petbot_platform.manifest import dumps, from_manifest, loads, to_manifest
from petbot_platform.registry import SkillNotFoundError, SkillRegistry

__all__ = [
    "SKILLS_GROUP",
    "InProcessDispatch",
    "SkillNotFoundError",
    "SkillRegistry",
    "build_registry",
    "dumps",
    "from_manifest",
    "load_skills",
    "loads",
    "to_manifest",
]
