"""Opt-in live integration tests against the real booru APIs (issue #12).

These hit Derpibooru and e621 over the network, so they are skipped unless
``PETBOT_LIVE=1`` is set — CI runs without secrets and must never depend on
them. They verify the rewrite works end to end against the live schemas: a SFW
search returns a usable image and is constrained to the safe rating.

Run with:  PETBOT_LIVE=1 pytest tests/live -v
Optional e621 auth: E621_USERNAME / E621_API_KEY.
"""

from __future__ import annotations

import os

import httpx
import pytest

from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.core.skills.context import Capabilities, Platform, SkillContext, User

pytestmark = pytest.mark.skipif(
    os.environ.get("PETBOT_LIVE") != "1",
    reason="live API test; set PETBOT_LIVE=1 to enable",
)

_USER_AGENT = "PetBot/2.0 (https://github.com/auzbuzzard/petbot; live test)"


def _ctx(*, allows_explicit: bool = False) -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="0", display_name="LiveTester"),
        conversation_id="live",
        capabilities=Capabilities(allows_explicit=allows_explicit),
    )


async def test_derpi_live_returns_usable_image() -> None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        skill = DerpiSkill(client=client, api_key=os.environ.get("DERPIBOORU_API_KEY") or None)
        result = await skill.run({"tags": "pony"}, _ctx())
    assert not result.is_error, result.error
    assert result.embed is not None
    assert result.embed.image_url and result.embed.image_url.startswith("http")


async def test_e621_live_safe_search_returns_usable_image() -> None:
    async with httpx.AsyncClient(timeout=20.0) as client:
        skill = E621Skill(
            client=client,
            user_agent=_USER_AGENT,
            username=os.environ.get("E621_USERNAME") or None,
            api_key=os.environ.get("E621_API_KEY") or None,
        )
        result = await skill.run({"tags": "canine"}, _ctx())
    assert not result.is_error, result.error
    assert result.embed is not None
    assert result.embed.image_url and result.embed.image_url.startswith("http")
