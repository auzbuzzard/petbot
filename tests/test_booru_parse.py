"""Tests for the booru providers, engine, and skills (no live API calls).

HTTP is mocked at the transport layer with ``respx``; request *shaping* is checked
by inspecting the ``httpx.Request`` that a provider builds (no network needed).
"""

from __future__ import annotations

import httpx
import pytest
import respx
from conftest import load_fixture, make_context

from petbot.core.capabilities.boorus import derpibooru, e621, tags
from petbot.core.capabilities.boorus.engine import run_search
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.types import SearchRequest
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill

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
    # Equality and inequality spell the same on both sites (negation is `-tag`).
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


# --- request shaping (inspect the built httpx.Request) ------------------------


async def test_e621_build_request_serializes_system_tags() -> None:
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)", username="u", api_key="k")
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
    assert req.headers["user-agent"] == "PetBot/2.0 (test)"
    assert req.headers["authorization"].startswith("Basic ")


async def test_e621_nsfw_omits_rating_and_no_auth_without_creds() -> None:
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
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


async def test_derpi_nsfw_no_tags_uses_wildcard() -> None:
    provider = derpibooru.DerpibooruProvider()
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


# --- engine (respx transport mock) -------------------------------------------


@respx.mock
async def test_run_search_renders_post() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_success"))
    )
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
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
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
    search = SearchRequest(tags=("x",), safe_only=False)
    async with httpx.AsyncClient() as client:
        with pytest.raises(SiteFailureStatusError) as exc:
            await run_search(provider, client, search, author="Rex")
    assert "more than 40 tags" in exc.value.site_message


@respx.mock
async def test_run_search_status_fallback_on_non_json_error() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(503, text="<html>down</html>")
    )
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
    async with httpx.AsyncClient() as client:
        with pytest.raises(SiteFailureStatusError) as exc:
            await run_search(provider, client, SearchRequest(tags=("x",)), author="Rex")
    assert "503" in exc.value.site_message


@respx.mock
async def test_run_search_2xx_non_json_raises_not_no_results() -> None:
    # A 200 with an undecodable body must surface as an error, not silent "no image".
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, text="<html>not json</html>")
    )
    provider = e621.E621Provider(user_agent="PetBot/2.0 (test)")
    async with httpx.AsyncClient() as client:
        with pytest.raises(SiteFailureStatusError):
            await run_search(provider, client, SearchRequest(tags=("x",)), author="Rex")


# --- skills end to end --------------------------------------------------------


@respx.mock
async def test_derpi_skill_sfw_constrains_to_safe() -> None:
    route = respx.get("https://derpibooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("derpibooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = DerpiSkill(client=client)
        result = await skill.run({"tags": "pony"}, make_context(allows_explicit=False))
    assert not result.is_error and result.embed is not None
    assert "safe" in route.calls.last.request.url.params["q"]


@respx.mock
async def test_skill_nsfw_does_not_inject_safe() -> None:
    route = respx.get("https://derpibooru.org/api/v1/json/search/images").mock(
        return_value=httpx.Response(200, json=load_fixture("derpibooru_success"))
    )
    async with httpx.AsyncClient() as client:
        skill = DerpiSkill(client=client)
        await skill.run({"tags": "pony"}, make_context(allows_explicit=True))
    assert route.calls.last.request.url.params["q"] == "pony"


@respx.mock
async def test_e621_skill_surfaces_failure() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(422, json=load_fixture("e621_error"))
    )
    async with httpx.AsyncClient() as client:
        skill = E621Skill(client=client, user_agent="PetBot/2.0 (test)")
        result = await skill.run({"tags": "x"}, make_context(allows_explicit=True))
    assert result.is_error and "e621 says" in (result.error or "")


@respx.mock
async def test_e621_skill_empty_is_friendly() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_empty"))
    )
    async with httpx.AsyncClient() as client:
        skill = E621Skill(client=client, user_agent="PetBot/2.0 (test)")
        result = await skill.run({"tags": "asdfqwer"}, make_context())
    assert not result.is_error and result.embed is None and result.text
