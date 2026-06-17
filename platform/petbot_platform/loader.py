"""Discover skills installed as ``petbot.skills`` entry-point plugins.

A runtime host calls :func:`build_registry` to assemble exactly the skills present
in *its* deployment — the brain worker installs some, the music worker others, the
edge none. Frontends never import skills; they read the manifest.
"""

from __future__ import annotations

import logging
from importlib.metadata import entry_points

from petbot_domain import Skill
from petbot_platform.registry import SkillRegistry

logger = logging.getLogger(__name__)

#: The entry-point group every skill package registers under.
SKILLS_GROUP = "petbot.skills"


def load_skills(group: str = SKILLS_GROUP) -> list[Skill]:
    """Load and instantiate every skill registered under ``group``.

    Each entry point names a zero-argument ``Skill`` class (or a factory returning
    one). Dependency-injected skills (those needing a client/config) are a later
    host concern; today only argument-free skills are constructed here.
    """
    skills: list[Skill] = []
    for ep in entry_points(group=group):
        target = ep.load()
        skill = target() if isinstance(target, type) else target
        if not isinstance(skill, Skill):
            raise TypeError(f"Entry point {ep.name!r} did not produce a Skill: {skill!r}")
        skills.append(skill)
    logger.debug("Loaded %d skill(s) from %r: %s", len(skills), group, [s.name for s in skills])
    return skills


def build_registry(group: str = SKILLS_GROUP) -> SkillRegistry:
    """Discover plugins under ``group`` and assemble a :class:`SkillRegistry`."""
    return SkillRegistry(load_skills(group))
