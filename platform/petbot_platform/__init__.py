"""PetBot runtime: skill discovery, registry, and manifest projection.

A *worker* uses :func:`build_registry` to load its installed skills and runs them
directly (``registry.get(name).run(...)``). An *edge* uses :mod:`.manifest` to
read skill descriptions without importing skills. The edge→worker hop itself is a
``DispatchPort`` (defined in ``petbot_domain``); its concrete, remote
implementation ships with the edge.
"""

from __future__ import annotations

from petbot_platform.loader import SKILLS_GROUP, build_registry, load_skills
from petbot_platform.manifest import dumps, from_manifest, loads, to_manifest
from petbot_platform.registry import SkillNotFoundError, SkillRegistry

__all__ = [
    "SKILLS_GROUP",
    "SkillNotFoundError",
    "SkillRegistry",
    "build_registry",
    "dumps",
    "from_manifest",
    "load_skills",
    "loads",
    "to_manifest",
]
