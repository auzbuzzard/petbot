"""The web skills: provider fallback for search, and the fetch skill's guards (no live web).

Tavily is mocked at the transport layer with ``respx``; ``ddgs`` and the page fetcher are
replaced by fakes so nothing leaves the process.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from ddgs.exceptions import DDGSException
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import BinaryContent

from petbot.domain import (
    EmptyResult,
    InvalidInput,
    Platform,
    SkillContext,
    UpstreamUnavailable,
    User,
)
from petbot.skills.web.fetch import WebFetchSkill
from petbot.skills.web.search import (
    TAVILY_URL,
    SearchHit,
    TavilyProvider,
    WebSearchSkill,
    format_hits,
)
from petbot.types import WebFetchArgs, WebSearchArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class _FakeProvider:
    def __init__(
        self, name: str, hits: list[SearchHit] | None = None, exc: Exception | None = None
    ) -> None:
        self.name = name
        self._hits = hits or []
        self._exc = exc
        self.queries: list[str] = []

    async def search(self, query: str) -> list[SearchHit]:
        self.queries.append(query)
        if self._exc is not None:
            raise self._exc
        return self._hits


_HIT = SearchHit(title="Gemma 4", url="https://ai.google.dev/gemma", snippet="Released in April.")


@respx.mock
async def test_tavily_sends_the_key_as_bearer_and_maps_results() -> None:
    route = respx.post(TAVILY_URL).respond(
        json={"results": [{"title": "T", "url": "https://x.test/a", "content": "body"}]}
    )
    async with httpx.AsyncClient() as client:
        hits = await TavilyProvider(client, "tvly-secret").search("q")
    assert hits == [SearchHit(title="T", url="https://x.test/a", snippet="body")]
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tvly-secret"
    assert b'"search_depth":"basic"' in request.content


async def test_search_returns_the_first_provider_with_hits() -> None:
    first, second = _FakeProvider("tavily", [_HIT]), _FakeProvider("ddgs", [_HIT])
    result = await WebSearchSkill([first, second]).run(WebSearchArgs(query=" gemma "), _ctx())
    assert result.text is not None and "<https://ai.google.dev/gemma>" in result.text
    assert first.queries == ["gemma"] and second.queries == []


@respx.mock
async def test_search_falls_back_when_tavily_is_out_of_quota() -> None:
    respx.post(TAVILY_URL).respond(status_code=432)
    fallback = _FakeProvider("ddgs", [_HIT])
    async with httpx.AsyncClient() as client:
        skill = WebSearchSkill([TavilyProvider(client, "k"), fallback])
        result = await skill.run(WebSearchArgs(query="gemma"), _ctx())
    assert fallback.queries == ["gemma"]
    assert result.text is not None and "Gemma 4" in result.text


async def test_search_falls_back_past_an_empty_provider() -> None:
    fallback = _FakeProvider("ddgs", [_HIT])
    await WebSearchSkill([_FakeProvider("tavily"), fallback]).run(WebSearchArgs(query="q"), _ctx())
    assert fallback.queries == ["q"]


async def test_search_raises_unavailable_when_every_provider_fails() -> None:
    skill = WebSearchSkill(
        [
            _FakeProvider("tavily", exc=httpx.ConnectError("down")),
            _FakeProvider("ddgs", exc=DDGSException("ratelimit")),
        ]
    )
    with pytest.raises(UpstreamUnavailable):
        await skill.run(WebSearchArgs(query="q"), _ctx())


async def test_search_raises_empty_when_providers_answer_with_nothing() -> None:
    with pytest.raises(EmptyResult):
        await WebSearchSkill([_FakeProvider("ddgs")]).run(WebSearchArgs(query="q"), _ctx())


async def test_search_rejects_a_blank_query() -> None:
    with pytest.raises(InvalidInput):
        await WebSearchSkill([_FakeProvider("ddgs", [_HIT])]).run(WebSearchArgs(query="  "), _ctx())


def test_format_hits_numbers_results_and_clips_snippets() -> None:
    text = format_hits("q", [SearchHit(title="A", url="https://a.test", snippet="x" * 1000)])
    lines = text.splitlines()
    assert lines[1] == "1. A — <https://a.test>"
    assert len(lines[2].strip()) <= 400 and lines[2].endswith("…")


# --- fetch --------------------------------------------------------------------


class _FakeFetch:
    def __init__(self, page: object) -> None:
        self._page = page

    async def __call__(self, url: str) -> object:
        if isinstance(self._page, Exception):
            raise self._page
        return self._page


def _fetch_skill(page: object) -> WebFetchSkill:
    skill = WebFetchSkill("PetBot/test")
    skill._fetch = _FakeFetch(page)  # type: ignore[assignment]
    return skill


async def test_fetch_returns_title_and_markdown() -> None:
    page = {"url": "https://a.test/p", "title": "Hello", "content": "# Hi\n\nbody"}
    result = await _fetch_skill(page).run(WebFetchArgs(url="https://a.test/p"), _ctx())
    assert result.text is not None
    assert "<https://a.test/p>" in result.text and "Title: Hello" in result.text
    assert "body" in result.text


async def test_fetch_failure_is_an_expected_error() -> None:
    skill = _fetch_skill(ModelRetry("Failed to fetch"))
    with pytest.raises(UpstreamUnavailable):
        await skill.run(WebFetchArgs(url="https://a.test"), _ctx())


async def test_fetch_rejects_binary_content() -> None:
    skill = _fetch_skill(BinaryContent(data=b"%PDF", media_type="application/pdf"))
    with pytest.raises(InvalidInput, match="application/pdf"):
        await skill.run(WebFetchArgs(url="https://a.test/f.pdf"), _ctx())


async def test_fetch_rejects_a_non_http_url() -> None:
    with pytest.raises(InvalidInput):
        await WebFetchSkill("PetBot/test").run(WebFetchArgs(url="file:///etc/passwd"), _ctx())


async def test_fetch_refuses_local_addresses() -> None:
    # The Lambda runtime API listens on localhost; the SSRF guard must refuse it.
    url = "http://127.0.0.1:9001/2018-06-01/runtime/invocation/next"
    with pytest.raises(UpstreamUnavailable):
        await WebFetchSkill("PetBot/test").run(WebFetchArgs(url=url), _ctx())
