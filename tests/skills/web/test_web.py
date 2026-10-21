"""The web skills: provider fallback for search, and the fetch skill's guards (no live web).

Tavily is mocked at the transport layer with ``respx``; ``ddgs`` and the page fetcher are
replaced by fakes so nothing leaves the process.
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx
from ddgs.exceptions import DDGSException
from pydantic_ai._ssrf import ResolvedUrl

from petbot.domain import (
    EmptyResult,
    InvalidInput,
    Platform,
    SkillContext,
    UpstreamUnavailable,
    User,
)
from petbot.skills.web import fetch as fetch_module
from petbot.skills.web.fetch import MAX_BYTES, WebFetchSkill
from petbot.skills.web.search import (
    TAVILY_URL,
    SearchHit,
    SearchResults,
    TavilyProvider,
    WebSearchSkill,
    format_results,
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
        self,
        name: str,
        hits: list[SearchHit] | None = None,
        exc: Exception | None = None,
        answer: str | None = None,
    ) -> None:
        self.name = name
        self._hits = hits or []
        self._exc = exc
        self._answer = answer
        self.queries: list[str] = []
        self.safe: list[bool] = []

    async def search(self, query: str, *, safe: bool) -> SearchResults:
        self.queries.append(query)
        self.safe.append(safe)
        if self._exc is not None:
            raise self._exc
        return SearchResults(hits=self._hits, answer=self._answer)


_HIT = SearchHit(title="Gemma 4", url="https://ai.google.dev/gemma", snippet="Released in April.")


@respx.mock
async def test_tavily_sends_the_key_as_bearer_and_maps_results() -> None:
    route = respx.post(TAVILY_URL).respond(
        json={"results": [{"title": "T", "url": "https://x.test/a", "content": "body"}]}
    )
    async with httpx.AsyncClient() as client:
        results = await TavilyProvider(client, "tvly-secret").search("q", safe=True)
    assert results == SearchResults(
        hits=[SearchHit(title="T", url="https://x.test/a", snippet="body")]
    )
    request = route.calls.last.request
    assert request.headers["authorization"] == "Bearer tvly-secret"
    assert b'"search_depth":"basic"' in request.content


@respx.mock
async def test_tavily_asks_for_its_answer_and_keeps_it() -> None:
    route = respx.post(TAVILY_URL).respond(
        json={
            "answer": " Today's daily is Minimum Operations to Sort a String (Medium). ",
            "results": [{"title": "T", "url": "https://x.test/a", "content": "body"}],
        }
    )
    async with httpx.AsyncClient() as client:
        results = await TavilyProvider(client, "k").search("q", safe=True)
    assert json.loads(route.calls.last.request.content)["include_answer"] == "advanced"
    assert results.answer == "Today's daily is Minimum Operations to Sort a String (Medium)."


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


def test_format_results_numbers_results_and_clips_snippets() -> None:
    hits = [SearchHit(title="A", url="https://a.test", snippet="x" * 1000)]
    lines = format_results("q", SearchResults(hits=hits)).splitlines()
    assert lines[1] == "1. A — <https://a.test> (date unknown)"
    assert len(lines[2].strip()) <= 400 and lines[2].endswith("…")
    assert "never state a date that isn't shown here" in lines[-1]
    assert "end your reply with the links you used" in lines[-1]


def test_format_results_shows_the_publication_date_when_known() -> None:
    hit = SearchHit(title="Gemma 3 270M", url="https://n.test", snippet="s", published="2025-08-14")
    lines = format_results("q", SearchResults(hits=[hit])).splitlines()
    assert lines[1].endswith("(published 2025-08-14)")


def test_format_results_leads_with_the_providers_answer() -> None:
    text = format_results("q", SearchResults(hits=[_HIT], answer="Gemma 4 came out in April."))
    lines = text.splitlines()
    assert lines[1] == "Answer, from the sources below: Gemma 4 came out in April."
    assert lines[2] == "Sources:"
    assert lines[3].startswith("1. Gemma 4 — <https://ai.google.dev/gemma>")


async def test_search_hands_the_answer_to_the_agent() -> None:
    provider = _FakeProvider("tavily", [_HIT], answer="Gemma 4 came out in April.")
    result = await WebSearchSkill([provider]).run(WebSearchArgs(query="gemma"), _ctx())
    assert result.text is not None and "Gemma 4 came out in April." in result.text


@respx.mock
async def test_tavily_asks_for_dates_and_safe_results_and_keeps_the_day() -> None:
    route = respx.post(TAVILY_URL).respond(
        json={
            "results": [
                {
                    "title": "T",
                    "url": "https://x.test/a",
                    "content": "c",
                    "published_date": "2025-08-14T09:00:00Z",
                },
                {"title": "U", "url": "https://x.test/b", "content": "c", "published_date": None},
            ]
        }
    )
    async with httpx.AsyncClient() as client:
        results = await TavilyProvider(client, "k").search("q", safe=True)
        await TavilyProvider(client, "k").search("q", safe=False)
    assert [h.published for h in results.hits] == ["2025-08-14", None]
    assert results.answer is None
    first, second = (json.loads(c.request.content) for c in route.calls)
    assert first["include_published_date"] is True
    assert (first["safe_search"], second["safe_search"]) == (True, False)


async def test_search_asks_for_safe_results_outside_age_gated_channels() -> None:
    provider = _FakeProvider("ddgs", [_HIT])
    skill = WebSearchSkill([provider])
    await skill.run(WebSearchArgs(query="q"), _ctx())
    await skill.run(WebSearchArgs(query="q"), _ctx().model_copy(update={"allows_explicit": True}))
    assert provider.safe == [True, False]


@respx.mock
async def test_tavily_null_title_does_not_crash_formatting() -> None:
    respx.post(TAVILY_URL).respond(
        json={"results": [{"title": None, "url": "https://x.test/a", "content": None}]}
    )
    async with httpx.AsyncClient() as client:
        result = await WebSearchSkill([TavilyProvider(client, "k")]).run(
            WebSearchArgs(query="q"), _ctx()
        )
    assert result.text is not None and "<https://x.test/a>" in result.text


def test_ddgs_no_results_is_empty_not_an_outage(monkeypatch: pytest.MonkeyPatch) -> None:
    from petbot.skills.web import search as search_module

    class _NoResults:
        def __init__(self, **kwargs: object) -> None: ...

        def text(self, query: str, **kwargs: object) -> list[dict[str, str]]:
            raise DDGSException("No results found.")

    monkeypatch.setattr(search_module, "DDGS", _NoResults)
    assert search_module.DdgsProvider()._search_sync("q", True) == SearchResults(hits=[])


def test_ddgs_engine_errors_still_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    from petbot.skills.web import search as search_module

    class _Broken:
        def __init__(self, **kwargs: object) -> None: ...

        def text(self, query: str, **kwargs: object) -> list[dict[str, str]]:
            raise DDGSException("Ratelimit")

    monkeypatch.setattr(search_module, "DDGS", _Broken)
    with pytest.raises(DDGSException):
        search_module.DdgsProvider()._search_sync("q", True)


# --- fetch --------------------------------------------------------------------
#
# DNS is stubbed to a public address so the SSRF guard passes offline; HTTP is mocked at
# the dialed IP (the fetcher connects by IP with the original Host header).

_IP = "93.184.215.14"


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(url: str, allow_local: bool) -> ResolvedUrl:
        from urllib.parse import urlparse

        parts = urlparse(url)
        assert not allow_local
        return ResolvedUrl(
            resolved_ip=_IP,
            hostname=parts.hostname or "",
            port=parts.port or 443,
            is_https=parts.scheme == "https",
            path=parts.path or "/",
        )

    monkeypatch.setattr(fetch_module, "validate_and_resolve_url", resolve)


async def _fetch(url: str) -> str:
    async with httpx.AsyncClient() as client:
        result = await WebFetchSkill(client, "PetBot/test").run(WebFetchArgs(url=url), _ctx())
    assert result.text is not None
    return result.text


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_fetch_converts_html_and_sends_the_original_host() -> None:
    route = respx.get(f"https://{_IP}/p").respond(
        html="<html><title> Hello </title><body><h1>Hi</h1><p>body</p></body></html>"
    )
    text = await _fetch("https://a.test/p")
    assert "<https://a.test/p>" in text and "Title: Hello" in text
    assert text.endswith("cite it as <https://a.test/p>.")
    assert "Hi" in text and "body" in text
    assert route.calls.last.request.headers["host"] == "a.test"


_ARTICLE = "The striped hyena is a species of hyena native to North and East Africa. " * 8
_NAV = "".join(f'<li><a href="/wiki/Page_{i}">Navigation link {i}</a></li>' for i in range(60))
_PAGE = f"""<html><head><title>Striped hyena</title>
<script type="application/ld+json">{{"@context": "https://schema.org", "@type": "Article"}}</script>
</head><body>
<nav><ul>{_NAV}</ul></nav>
<main><article><h1>Striped hyena</h1><p>{_ARTICLE}</p>
<h2>Conservation</h2><p>It is listed as Near Threatened on the IUCN Red List.
The global population is estimated at under 10,000 mature individuals.</p></article></main>
<footer>{"".join(f'<a href="/f/{i}">Footer link {i}</a> ' for i in range(40))}</footer>
</body></html>"""


def test_to_markdown_keeps_the_article_not_the_navigation() -> None:
    title, text = fetch_module.to_markdown("text/html", _PAGE, "https://a.test/wiki/Striped_hyena")
    assert title == "Striped hyena"
    assert "Near Threatened" in text and "native to North and East Africa" in text
    assert "Navigation link" not in text and "Footer link" not in text
    assert "](" not in text and "schema.org" not in text  # no link markup, no JSON-LD


def test_to_markdown_falls_back_to_visible_text_without_main_content() -> None:
    _, text = fetch_module.to_markdown(
        "text/html", "<html><body><a href='/x'>Sign in</a></body></html>", "https://a.test"
    )
    assert text == "Sign in"


def test_to_markdown_passes_non_html_text_through() -> None:
    assert fetch_module.to_markdown("text/plain", "plain words", "https://a.test") == (
        "",
        "plain words",
    )


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_fetch_follows_a_redirect_through_the_guard() -> None:
    respx.get(f"https://{_IP}/old").respond(301, headers={"location": "https://b.test/new"})
    respx.get(f"https://{_IP}/new").respond(
        text="moved here", headers={"content-type": "text/plain"}
    )
    text = await _fetch("https://a.test/old")
    assert "<https://b.test/new>" in text and "moved here" in text


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_fetch_rejects_binary_without_downloading_it() -> None:
    respx.get(f"https://{_IP}/f.pdf").respond(
        content=b"%PDF", headers={"content-type": "application/pdf"}
    )
    with pytest.raises(InvalidInput, match="application/pdf"):
        await _fetch("https://a.test/f.pdf")


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_fetch_stops_reading_past_the_size_cap() -> None:
    respx.get(f"https://{_IP}/huge").respond(
        content=b"x" * (MAX_BYTES + 1), headers={"content-type": "text/plain"}
    )
    with pytest.raises(InvalidInput, match="too big"):
        await _fetch("https://a.test/huge")


@respx.mock
@pytest.mark.usefixtures("public_dns")
async def test_fetch_http_error_is_unavailable() -> None:
    respx.get(f"https://{_IP}/gone").respond(404)
    with pytest.raises(UpstreamUnavailable):
        await _fetch("https://a.test/gone")


async def test_fetch_rejects_a_non_http_url() -> None:
    with pytest.raises(InvalidInput):
        await _fetch("file:///etc/passwd")


async def test_fetch_refuses_local_addresses() -> None:
    # The Lambda runtime API listens on localhost; the SSRF guard must refuse it.
    with pytest.raises(UpstreamUnavailable):
        await _fetch("http://127.0.0.1:9001/2018-06-01/runtime/invocation/next")


@respx.mock
async def test_fetch_refuses_a_redirect_into_a_local_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pydantic_ai._ssrf import validate_and_resolve_url as real

    async def resolve(url: str, allow_local: bool) -> ResolvedUrl:
        if "a.test" in url:
            return ResolvedUrl(_IP, "a.test", 443, True, "/r")
        return await real(url, allow_local)

    monkeypatch.setattr(fetch_module, "validate_and_resolve_url", resolve)
    respx.get(f"https://{_IP}/r").respond(302, headers={"location": "http://127.0.0.1:9001/x"})
    with pytest.raises(UpstreamUnavailable):
        await _fetch("https://a.test/r")
