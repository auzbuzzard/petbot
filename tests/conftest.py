"""Shared test helpers: fixture loading and a neutral SkillContext factory.

External booru APIs are never hit live — tests mock HTTP at the transport layer
with ``respx`` (see ``tests/test_booru_parse.py``) and replay saved JSON fixtures,
keeping the NSFW-content APIs out of CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from petbot.core.skills.context import Capabilities, Platform, SkillContext, User
from petbot.core.skills.ports import VoicePort

FIXTURES = Path(__file__).parent / "fixtures"


def make_context(
    *,
    allows_explicit: bool = False,
    supports_voice: bool = False,
    voice: VoicePort | None = None,
    display_name: str = "Tester",
    user_id: str = "42",
    conversation_id: str = "conv-1",
) -> SkillContext:
    """Construct a :class:`SkillContext` for tests without a live frontend."""
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id=user_id, display_name=display_name),
        conversation_id=conversation_id,
        capabilities=Capabilities(allows_explicit=allows_explicit, supports_voice=supports_voice),
        voice=voice,
    )


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by file name (the .json suffix is optional)."""
    filename = name if name.endswith(".json") else f"{name}.json"
    data: dict[str, Any] = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return data
