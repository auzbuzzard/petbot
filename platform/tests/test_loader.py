"""The loader discovers installed ``petbot.skills`` plugins."""

from __future__ import annotations

from petbot_platform import build_registry


def test_build_registry_discovers_installed_math_plugin() -> None:
    registry = build_registry()
    assert "math" in {skill.name for skill in registry}
