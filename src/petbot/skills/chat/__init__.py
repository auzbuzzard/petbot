"""The chat skill package: PetBot's conversational LLM agent + the slash stylizer.

The chat agent needs a :class:`petbot.types.Skills` client for its sibling-skill
tools, so the core worker builds it explicitly with a ``SkillsClient`` over a local
transport bound to that same worker, then registers it. ``LLMStyleProvider`` is the
persona for the LLM-free slash path — the worker holds it and applies it per request
(it is a :class:`~petbot.domain.StyleProvider`, not a dispatched skill).
"""

from __future__ import annotations

from petbot.skills.chat.skill import ChatSkill
from petbot.skills.chat.stylize import LLMStyleProvider, Stylist

__all__ = ["ChatSkill", "LLMStyleProvider", "Stylist"]
