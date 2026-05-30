"""Live integration tests against the real Derpibooru and e621 APIs.

These are **off by default** — they require outbound network access to
``derpibooru.org`` / ``e926.net`` (not in the default sandbox allowlist) and so
are skipped in CI. Run them deliberately once those hosts are reachable:

    PETBOT_LIVE=1 pytest tests/live -v
    # or
    pytest tests/live -v --run-live

They prove the providers parse *real* responses end-to-end: a real HTTP call
through ``aiohttp`` → provider parsing → a neutral ``SkillResult`` with a usable
image URL. Only safe content is requested (e926, Derpibooru default filter).
"""

from __future__ import annotations

import os
from typing import cast

import aiohttp
import pytest

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.capabilities.boorus.datastruct import HttpSession

pytestmark = pytest.mark.live

_LIVE_USER_AGENT = os.environ.get(
    "USER_AGENT", "PetBot/2.0 (live integration test; https://github.com/auzbuzzard/petbot)"
)


async def test_derpibooru_live_search_returns_a_usable_embed() -> None:
    async with aiohttp.ClientSession() as session:
        result = await derpibooru.search(
            "safe, pony",
            session=cast(HttpSession, session),
            allows_explicit=False,
            author="LiveTest",
        )
    assert not result.is_error, result.error
    assert result.embed is not None
    assert (result.embed.title or "").strip()
    assert (result.embed.image_url or "").startswith("https://"), result.embed.image_url
    assert result.embed.author_name == "Derpibooru"


async def test_e926_live_search_returns_a_usable_embed() -> None:
    async with aiohttp.ClientSession() as session:
        result = await e621.search(
            "canine",
            session=cast(HttpSession, session),
            allows_explicit=False,  # forces the safe e926 mirror
            author="LiveTest",
            user_agent=_LIVE_USER_AGENT,
            username=os.environ.get("E621_USERNAME"),
            api_key=os.environ.get("E621_API_KEY"),
        )
    assert not result.is_error, result.error
    assert result.embed is not None
    assert result.embed.author_name == "e926"
    # A real safe post should carry an https image; tolerate the rare null-URL post.
    image_url = result.embed.image_url or ""
    assert image_url == "" or image_url.startswith("https://"), image_url
