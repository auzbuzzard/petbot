"""Tests for the booru providers, engine, and skills (no live API calls).

HTTP is mocked at the transport layer with ``respx``; request *shaping* is checked
by inspecting the ``httpx.Request`` that a provider builds (no network needed).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from conftest import load_fixture, make_context
from petbot.skills.booru import derpibooru, e621, furbooru, philomena, tags
from petbot.skills.booru.engine import run_search
from petbot.skills.booru.errors import SiteFailureStatusError
from petbot.skills.booru.skill import DerpiSkill, E621Skill, FurbooruSkill, _build_search
from petbot.skills.booru.types import SearchRequest
from petbot.types import BooruArgs

# --- abstract vocabulary ------------------------------------------------------


def test_provider_enums_subclass_the_abstract_bases() -> None:
    assert issubclass(e621.Sort, tags.Sort) and issubclass(derpibooru.Sort, tags.Sort)
    assert isinstance(e621.Sort.favorites, tags.Sort)
    assert e621.Sort.favorites.value == "favcount"  # member .value is the wire token


def test_vocabulary_is_per_site_and_full_native() -> None:
    assert "wilson_score" in {s.value for s in derpibooru.Sort}
    assert "wilson_score" not in {s.value for s in e621.Sort}
    assert "hot" in {s.value for s in e621.Sort}
    assert "suggestive" in {r.value for r in derpibooru.Rating}  # Derpi-only
    assert "suggestive" not in {r.value for r in e621.Rating}
    # Derpibooru has MLP-specific tiers; Furbooru does not
    assert "grimdark" in {r.value for r in derpibooru.Rating}
    assert "grimdark" not in {r.value for r in furbooru.Rating}
    assert "suggestive" in {r.value for r in furbooru.Rating}


def test_philomena_sort_and_filetype_shared_across_sites() -> None:
    assert derpibooru.Sort is philomena.Sort
    assert furbooru.Sort is philomena.Sort
    assert derpibooru.FileType is philomena.FileType
    assert furbooru.FileType is philomena.FileType


def test_range_serialization_dialects() -> None:
    r = tags.NumericFilter(at_least=100, at_most=200)
    assert tags.operator_filter("score", r) == ["score:>=100", "score:<=200"]
    assert tags.dotted_filter("score", r) == ["score.gte:100", "score.lte:200"]
    assert tags.operator_filter("score", None) == []
    assert tags.operator_filter("score", tags.NumericFilter()) == []


def test_range_exclusive_bounds() -> None:
    r = tags.NumericFilter(greater_than=10, less_than=20)
    assert tags.operator_filter("score", r) == ["score:>10", "score:<20"]
    assert tags.dotted_filter("score", r) == ["score.gt:10", "score.lt:20"]
    assert bool(tags.NumericFilter(less_than=5)) is True


def test_numeric_filter_eq_and_ne() -> None:
    assert tags.operator_filter("score", tags.NumericFilter(eq=100)) == ["score:100"]
    assert tags.dotted_filter("score", tags.NumericFilter(eq=100)) == ["score:100"]
    assert tags.operator_filter("score", tags.NumericFilter(ne=5)) == ["-score:5"]
    assert tags.dotted_filter("faves", tags.NumericFilter(ne=5)) == ["-faves:5"]


def test_parse_tags_follows_site_convention() -> None:
    assert e621.E621Provider(user_agent="x").parse_tags("twilight_sparkle canine") == (
        "twilight_sparkle",
        "canine",
    )
    assert derpibooru.DerpibooruProvider().parse_tags("twilight sparkle, safe") == (
        "twilight sparkle",
        "safe",
    )
    assert furbooru.FurbooruProvider().parse_tags("wolf, canine") == ("wolf", "canine")


# --- request shaping (inspect the built httpx.Request) ------------------------


async def test_e621_build_request_serializes_system_tags() -> None:
    provider = e621.E621Provider(user_agent="PetBot/2.1 (test)", username="u", api_key="k")
    search = SearchRequest(
        tags=("canine", "forest"),
        safe_only=True,
        sort=e621.Sort.favorites,
        score=tags.NumericFilter(at_least=100),
        file_type=e621.FileType.png,
    )
    async with httpx.AsyncClient() as client:
        req = provider.build_request(client, search)
    tag_param = req.url.params["tags"]
    assert tag_param.split() == [
        "canine",
        "forest",
        "rating:s",
        "order:favcount",
        "type:png",
        "score:>=100",
    ]
    assert req.url.params["limit"] == "1"
    assert req.headers["user-agent"] == "PetBot/2.1 (test)"
    assert req.headers["authorization"].startswith("Basic ")


def test_default_sort_is_random_on_both_providers() -> None:
    ctx = make_context()
    e621_search = _build_search(e621.E621Provider(user_agent="x"), BooruArgs(tags="hyena"), ctx)
    derpi_search = _build_search(derpibooru.DerpibooruProvider(), BooruArgs(tags="pinkie pie"), ctx)
    assert e621_search.sort is e621.Sort.random
    assert derpi_search.sort is derpibooru.Sort.random


async def test_e621_nsfw_omits_rating_and_no_auth_without_creds() -> None:
    provider = e621.E621Provider(user_agent="PetBot/2.1 (test)")
    search = SearchRequest(tags=("canine",), safe_only=False)
    async with httpx.AsyncClient() as client:
        req = provider.build_request(client, search)
    assert "rating:" not in req.url.params["tags"]
    assert "authorization" not in req.headers


async def test_derpi_build_request_uses_q_and_dotted_ranges() -> None:
    provider = derpibooru.DerpibooruProvider(api_key="k")
    search = SearchRequest(
        tags=("twilight sparkle",),
        safe_only=True,
        sort=derpibooru.Sort.favorites,
        score=tags.NumericFilter(at_least=100),
    )
    async with httpx.AsyncClient() as client:
        req = provider.build_request(client, search)
    assert req.url.params["q"] == "twilight sparkle,safe,score.gte:100"
    assert req.url.params["sf"] == "faves"
    assert req.url.params["per_page"] == "1"
    assert req.url.params["filter_id"] == "56027"
    assert req.url.params["key"] == "k"


async def test_derpi_sort_direction_is_caller_controlled() -> None:
    provider = derpibooru.DerpibooruProvider()
    async with httpx.AsyncClient() as client:
        desc = provider.build_request(client, SearchRequest(tags=("a",), descending=True))
        asc = provider.build_request(client, SearchRequest(tags=("a",), descending=False))
    assert desc.url.params["sd"] == "desc"
    assert asc.url.params["sd"] == "asc"


async def test_furbooru_build_request_uses_filter_id_2() -> None:
    provider = furbooru.FurbooruProvider(api_key="k")
    search = SearchRequest(
        tags=("wolf",),
        safe_only=True,
        sort=philomena.Sort.favorites,
        score=tags.NumericFilter(at_least=10),
    )
    async with httpx.AsyncClient() as client:
        req = provider.build_request(client, search)
    assert req.url.params["q"] == "wolf,safe,score.gte:10"
    assert req.url.params["sf"] == "faves"
    assert req.url.params["filter_id"] == "2"
    assert req.url.params["key"] == "k"
    assert "furbooru.org" in req.url.host


async def test_furbooru_sort_direction_is_caller_controlled() -> None:
    provider = furbooru.FurbooruProvider()
    async with httpx.AsyncClient() as client:
        desc = provider.build_request(client, SearchRequest(tags=("a",), descending=True))
        asc = provider.build_request(client, SearchRequest(tags=("a",), descending=False))
    assert desc.url.params["sd"] == "desc"
    assert asc.url.params["sd"] == "asc"


async def test_furbooru_nsfw_no_tags_uses_wildcard() -> None:
    provider = furbooru.FurbooruProvider()
    async with httpx.AsyncClient() as client:
        req = provider.build_request(client, SearchRequest(tags=(), safe_only=False))
    assert req.url.params["q"] == "*"
    assert "key" not in req.url.params


# --- response decoding --------------------------------------------------------


def test_e621_parse() -> None:
    post = e621.E621Provider(user_agent="x").parse(load_fixture("e621_success"))
    assert post is not None
    assert post.post_id == 998877
    assert post.is_safe is True
    assert post.score == 290
    assert post.page_url == "https://e621.net/posts/998877"


def test_derpi_parse() -> None:
    post = derpibooru.DerpibooruProvider().parse(load_fixture("derpibooru_success"))
    assert post is not None
    assert post.post_id == 123456
    assert post.total == 42
    assert post.is_safe is True
    assert post.color == 0x00FF00


def test_furbooru_parse() -> None:
    post = furbooru.FurbooruProvider().parse(load_fixture("furbooru_success"))
    assert post is not None
    assert post.post_id == 654321
    assert post.total == 17
    assert post.is_safe is True
    assert post.color == 0x00FF00
    assert post.page_url == "https://furbooru.org/654321"
    assert post.site_name == "Furbooru"


def test_furbooru_absolutizes_protocol_relative_url() -> None:
    body = {
        "total": 1,
        "images": [{"id": 9, "representations": {"large": "//furbooru.org/img/large.png"}}],
    }
    post = furbooru.FurbooruProvider().parse(body)
    assert post is not None
    assert post.image_url == "https://furbooru.org/img/large.png"


def test_parse_none_on_empty_or_blocked() -> None:
    e = e621.E621Provider(user_agent="x")
    assert e.parse(load_fixture("e621_empty")) is None
    assert e.parse(load_fixture("e621_null_url")) is None
    assert derpibooru.DerpibooruProvider().parse(load_fixture("derpibooru_empty")) is None


def test_error_extraction() -> None:
    e = e621.E621Provider(user_agent="x")
    assert (
        e.error(load_fixture("e621_error")) == "You cannot search for more than 40 tags at a time."
    )
    assert e.error(load_fixture("e621_success")) is None
    d = derpibooru.DerpibooruProvider()
    assert d.error(load_fixture("derpibooru_error")) == "Imbalanced parentheses."
    assert d.error(load_fixture("derpibooru_success")) is None
    f = furbooru.FurbooruProvider()
    assert f.error(load_fixture("derpibooru_error")) == "Imbalanced parentheses."  # same schema
    assert f.error(load_fixture("furbooru_success")) is None


# --- engine (respx transport mock) -------------------------------------------


@respx.mock
async def test_run_search_renders_post() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_success"))
    )
    provider = e621.E621Provider(user_agent="PetBot/2.1 (test)")
    search = SearchRequest(tags=("canine",), safe_only=True)
    async with httpx.AsyncClient() as client:
        result = await run_search(provider, client, search, author="Rex")
    assert not result.is_error
    assert result.embed is not None and result.embed.author_name == "e621"


@respx.mock
async def test_run_search_surfaces_site_error_body() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(422, json=load_fixture("e621_error"))
    )
    provider = e621.E621Provider(user_agent="PetBot/2.1 (test)")
    async with httpx.AsyncClient() as client:
        with pytest.raises(SiteFailureStatusError) as exc:
            await run_search(
                provider, client, SearchRequest(tags=("x",), safe_only=False), author="Rex"
            )
    assert "more than 40 tags" in exc.value.site_message


# --- skills end to end --------------------------------------------------------


@respx.mock
async def test_derpi_skill_sfw_constrains_to_safe() -> None:
    route = respx.get("https://derpibooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("derpibooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = DerpiSkill(client=client)
        result = await skill.run(BooruArgs(tags="pony"), make_context(allows_explicit=False))
    assert not result.is_error and result.embed is not None
    assert "safe" in route.calls.last.request.url.params["q"]


@respx.mock
async def test_skill_nsfw_does_not_inject_safe() -> None:
    route = respx.get("https://derpibooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("derpibooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = DerpiSkill(client=client)
        await skill.run(BooruArgs(tags="pony"), make_context(allows_explicit=True))
    assert route.calls.last.request.url.params["q"] == "pony"


@respx.mock
async def test_furbooru_skill_sfw_constrains_to_safe() -> None:
    route = respx.get("https://furbooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("furbooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = FurbooruSkill(client=client)
        result = await skill.run(BooruArgs(tags="wolf"), make_context(allows_explicit=False))
    assert not result.is_error and result.embed is not None
    assert "safe" in route.calls.last.request.url.params["q"]
    assert route.calls.last.request.url.params["filter_id"] == "2"


@respx.mock
async def test_furbooru_skill_nsfw_does_not_inject_safe() -> None:
    route = respx.get("https://furbooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("furbooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = FurbooruSkill(client=client)
        await skill.run(BooruArgs(tags="wolf"), make_context(allows_explicit=True))
    assert route.calls.last.request.url.params["q"] == "wolf"


@respx.mock
async def test_e621_skill_surfaces_failure() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(422, json=load_fixture("e621_error"))
    )
    async with httpx.AsyncClient() as client:
        skill = E621Skill(client=client, user_agent="PetBot/2.1 (test)")
        result = await skill.run(BooruArgs(tags="x"), make_context(allows_explicit=True))
    assert result.is_error and "e621 says" in (result.error or "")


@respx.mock
async def test_e621_skill_empty_is_friendly() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_empty"))
    )
    async with httpx.AsyncClient() as client:
        skill = E621Skill(client=client, user_agent="PetBot/2.1 (test)")
        result = await skill.run(BooruArgs(tags="asdfqwer"), make_context())
    assert not result.is_error and result.embed is None and result.text
