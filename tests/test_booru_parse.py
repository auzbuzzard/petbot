"""Tests for the booru providers, engine, and skills (no live API calls)."""

from __future__ import annotations

import pytest
from conftest import FakeSession, load_fixture, make_context

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.capabilities.boorus.engine import run_search
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.types import SearchRequest, parse_tags
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill

# --- neutral helpers ----------------------------------------------------------


def test_parse_tags_splits_and_strips() -> None:
    assert parse_tags("pony, twilight sparkle ,  ") == ["pony", "twilight sparkle"]
    assert parse_tags("") == []


def test_sort_and_rating_vocabulary_is_per_site() -> None:
    # Each site advertises only its own system-tag vocabulary.
    assert "wilson_score" in {s.value for s in derpibooru.Sort}
    assert "favcount" not in {s.value for s in derpibooru.Sort}
    assert "favcount" in {s.value for s in e621.Sort}
    assert "wilson_score" not in {s.value for s in e621.Sort}
    assert "suggestive" in {r.value for r in derpibooru.Rating}
    assert "suggestive" not in {r.value for r in e621.Rating}


# --- request shaping: the safety floor ----------------------------------------


def test_derpi_request_safe_only_injects_safe_term() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    provider = derpibooru.DerpibooruProvider(api_key="k")
    search = SearchRequest(tags=("pony",), safe_only=True)
    provider.request(session, search, sort=derpibooru.Sort.score)
    params = session.calls[0]["params"]
    assert params["q"] == "pony,safe"
    assert params["sf"] == "score"
    assert params["filter_id"] == derpibooru.DerpibooruProvider._FILTER_EVERYTHING
    assert params["key"] == "k"


def test_derpi_request_nsfw_omits_rating_and_falls_back_to_wildcard() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    provider = derpibooru.DerpibooruProvider()
    provider.request(session, SearchRequest(tags=(), safe_only=False))
    params = session.calls[0]["params"]
    assert params["q"] == "*"  # no tags, all ratings
    assert "key" not in params


def test_e621_request_safe_only_adds_rating_tag_and_headers() -> None:
    session = FakeSession(load_fixture("e621_success"))
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)", username="u", api_key="k")
    provider.request(session, SearchRequest(tags=("canine",), safe_only=True), sort=e621.Sort.score)
    call = session.calls[0]
    assert call["url"] == "https://e621.net/posts.json"
    assert call["params"]["tags"] == "canine order:score rating:s"
    assert call["headers"]["User-Agent"] == "PetBot/2.0 (test)"
    assert call["auth"] is not None


def test_e621_request_nsfw_has_no_rating_tag() -> None:
    session = FakeSession(load_fixture("e621_success"))
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
    provider.request(session, SearchRequest(tags=("canine",), safe_only=False))
    call_tags = session.calls[0]["params"]["tags"]
    assert "rating:" not in call_tags
    assert session.calls[0]["auth"] is None  # no credentials → no basic auth


# --- response decoding --------------------------------------------------------


def test_derpi_response_to_post() -> None:
    post = derpibooru.Response.model_validate(load_fixture("derpibooru_success")).to_post()
    assert post is not None
    assert post.post_id == 123456
    assert post.image_url.endswith("/full.png")
    assert post.is_safe is True
    assert post.color == derpibooru._COLOR[derpibooru.Rating.safe]
    assert post.total == 42
    assert post.page_url == "https://derpibooru.org/123456"


def test_e621_response_to_post() -> None:
    post = e621.Response.model_validate(load_fixture("e621_success")).to_post()
    assert post is not None
    assert post.post_id == 998877
    assert post.is_safe is True
    assert post.score == 290
    assert post.favorites == 256
    assert post.file_ext == "jpg"
    assert post.total is None  # e621 reports no match count
    assert post.page_url == "https://e621.net/posts/998877"


def test_to_post_none_when_empty() -> None:
    assert derpibooru.Response.model_validate(load_fixture("derpibooru_empty")).to_post() is None
    assert e621.Response.model_validate(load_fixture("e621_empty")).to_post() is None


def test_e621_null_url_post_is_skipped() -> None:
    # A blocked post with null file/sample urls is unusable → no result.
    assert e621.Response.model_validate(load_fixture("e621_null_url")).to_post() is None


# --- error bodies -------------------------------------------------------------


def test_error_models_extract_reason() -> None:
    assert (
        e621.Error.model_validate(load_fixture("e621_error")).reason()
        == "You cannot search for more than 40 tags at a time."
    )
    assert (
        derpibooru.Error.model_validate(load_fixture("derpibooru_error")).reason()
        == "Imbalanced parentheses."
    )


def test_error_models_return_none_on_success_bodies() -> None:
    # reason() must be safe to call on a success body (it is, on every response).
    assert e621.Error.model_validate(load_fixture("e621_success")).reason() is None
    assert derpibooru.Error.model_validate(load_fixture("derpibooru_success")).reason() is None


async def test_run_search_raises_on_site_error() -> None:
    session = FakeSession(load_fixture("e621_error"))
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
    search = SearchRequest(tags=("x",), safe_only=False)
    response = provider.request(session, search)
    with pytest.raises(SiteFailureStatusError) as excinfo:
        await run_search(provider, response, search, author="Rex")
    assert "more than 40 tags" in excinfo.value.site_message


# --- skills end to end --------------------------------------------------------


async def test_derpi_skill_sfw_builds_safe_embed() -> None:
    session = FakeSession(load_fixture("derpibooru_success"))
    skill = DerpiSkill(session=session)
    result = await skill.run({"tags": "pony"}, make_context(allows_explicit=False))
    assert not result.is_error
    assert result.embed is not None
    assert result.embed.author_name == "Derpibooru"
    assert "42 results" in (result.embed.title or "")
    # SFW context → the request was constrained to the safe rating.
    assert "safe" in session.calls[0]["params"]["q"]


async def test_skill_safe_only_follows_capability() -> None:
    # NSFW context → no safe term injected.
    session = FakeSession(load_fixture("derpibooru_success"))
    skill = DerpiSkill(session=session)
    await skill.run({"tags": "pony"}, make_context(allows_explicit=True))
    assert session.calls[0]["params"]["q"] == "pony"


async def test_e621_skill_surfaces_site_failure() -> None:
    session = FakeSession(load_fixture("e621_error"))
    skill = E621Skill(session=session, user_agent="PetBot/2.0 (test)")
    result = await skill.run({"tags": "x"}, make_context(allows_explicit=True))
    assert result.is_error
    assert "e621 says" in (result.error or "")


async def test_e621_skill_empty_returns_friendly_message() -> None:
    session = FakeSession(load_fixture("e621_empty"))
    skill = E621Skill(session=session, user_agent="PetBot/2.0 (test)")
    result = await skill.run({"tags": "asdfqwer"}, make_context(allows_explicit=False))
    assert not result.is_error
    assert result.embed is None
    assert result.text
