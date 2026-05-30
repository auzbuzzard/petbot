"""Tests for the skill registry, especially capability-based filtering."""

from __future__ import annotations

import pytest

from petbot.core.skills.context import Capabilities
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.music_skill import MusicSkill
from petbot.core.skills.registry import SkillNotFoundError, SkillRegistry


def make_registry() -> SkillRegistry:
    return SkillRegistry([MusicSkill(), MathSkill()])


def test_get_by_name() -> None:
    registry = make_registry()
    assert registry.get("math").name == "math"


def test_get_unknown_raises() -> None:
    with pytest.raises(SkillNotFoundError):
        make_registry().get("nope")


def test_duplicate_names_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        SkillRegistry([MathSkill(), MathSkill()])


def test_iteration_is_sorted_by_name() -> None:
    names = [skill.name for skill in make_registry()]
    assert names == sorted(names)
    assert names == ["math", "music"]


def test_voice_skill_hidden_without_voice_capability() -> None:
    available = make_registry().available_for(Capabilities(supports_voice=False))
    assert [s.name for s in available] == ["math"]


def test_voice_skill_offered_with_voice_capability() -> None:
    available = make_registry().available_for(Capabilities(supports_voice=True))
    assert {s.name for s in available} == {"math", "music"}
