"""Tests for the modernized booru providers and skills (no live API calls)."""

from __future__ import annotations

from typing import Any

from conftest import FakeSession, load_fixture, make_context

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill

# --- argument parsing ---------------------------------------------------------


def test_derpi_parse_args_splits_tags_and_flags() -> None:
    args, tags = derpibooru.parse_args("--e --sort_score pony, twilight sparkle")
    assert args["explicit"] is True
    assert args["order"] is derpibooru.Order.score
    assert tags == ["pony", "twilight sparkle"]


def test_derpi_parse_args_default_safe() -> None:
    args, tags = derpibooru.parse_args("apple")
    assert args["explicit"] is False
    assert tags == ["apple"]


def test_e621_parse_args_explicit_flag() -> None:
    args, tags = e621.parse_args("--e canine, forest")
    assert args["explicit"] is True
    assert tags == ["canine", "forest"]


# --- derpibooru search end to end (faked HTTP) --------------------------------


async def test_derpi_search_success_builds_embed() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    result = await derpibooru.search("pony", session=session, allows_explicit=False, author="Spike")
    assert not result.is_error
    assert result.embed is not None
    assert result.embed.author_name == "Derpibooru"
    assert "42 results" in (result.embed.title or "")
    assert result.embed.color == derpibooru._COLOR_SAFE


async def test_derpi_search_empty_returns_friendly_message() -> None:
    session = FakeSession(load_fixture("derpibooru_empty"))
    result = await derpibooru.search(
        "asdfqwer", session=session, allows_explicit=False, author="Spike"
    )
    assert not result.is_error
    assert result.embed is None
    assert result.text


async def test_derpi_explicit_blocked_without_capability() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    result = await derpibooru.search(
        "--e pony", session=session, allows_explicit=False, author="Spike"
    )
    assert result.is_error
    assert "NSFW" in (result.error or "")
    # The request must never even be issued when explicit is disallowed.
    assert session.calls == []


# --- e621 search end to end (faked HTTP) --------------------------------------


async def test_e621_sends_user_agent_and_uses_safe_mirror() -> None:
    session = FakeSession(load_fixture("e621_success"))
    result = await e621.search(
        "canine",
        session=session,
        allows_explicit=False,
        author="Rex",
        user_agent="PetBot/2.0 (test)",
        username="u",
        api_key="k",
    )
    assert not result.is_error
    call = session.calls[0]
    assert call["url"].startswith("https://e926.net/")  # safe mirror
    assert call["headers"]["User-Agent"] == "PetBot/2.0 (test)"
    assert call["auth"] is not None  # basic auth supplied


async def test_e621_skill_surfaces_site_failure() -> None:
    session = FakeSession(load_fixture("e621_error"))
    skill = E621Skill(session=session, user_agent="PetBot/2.0 (test)")
    result = await skill.run({"tags": "x"}, make_context(allows_explicit=True))
    assert result.is_error
    assert "e621 says" in (result.error or "")


async def test_derpi_skill_uses_context_nsfw_flag() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    skill = DerpiSkill(session=session)
    # Explicit requested but channel is SFW -> blocked.
    blocked = await skill.run({"tags": "--e pony"}, make_context(allows_explicit=False))
    assert blocked.is_error


def test_e621_rating_parsing() -> None:
    payload: dict[str, Any] = load_fixture("e621_success")
    result = e621.image(payload)
    assert result is not None
    assert result.rating is e621.Rating.safe
    assert result.is_explicit is False
