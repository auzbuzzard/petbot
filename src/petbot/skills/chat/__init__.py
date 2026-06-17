"""The chat skill package: PetBot's conversational LLM agent.

No auto-discovery entry point: the skill needs a :class:`petbot.types.Skills`
client (its sibling-skill tools), so the core worker builds it explicitly with a
``SkillsClient`` over a local transport bound to that same worker, then registers it.
"""

from __future__ import annotations

from petbot.skills.chat.skill import ChatSkill

__all__ = ["ChatSkill"]
