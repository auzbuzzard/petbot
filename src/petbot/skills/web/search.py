"""The ``web_search`` skill: ranked providers, first one that answers wins.

Tavily (keyed, built for LLM consumers) runs first; ``ddgs`` (keyless metasearch over
public result pages) is the fallback for a missing key, an exhausted quota, or an outage.
The sources come back as a compact numbered list the agent cites from, each with its
publication date when the provider knows it and marked undated when it doesn't, so the
model never has to guess when a snippet was written.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import httpx
from ddgs import DDGS
from ddgs.exceptions import DDGSException

from petbot.domain import (
    EmptyResult,
    InvalidInput,
    Skill,
    SkillContext,
    SkillResult,
    UpstreamUnavailable,
)
from petbot.types import WebSearchArgs

logger = logging.getLogger(__name__)

#: Results per search: enough to cross-check, few enough to keep the prompt small.
MAX_RESULTS = 5
MAX_SNIPPET = 400
MAX_ANSWER = 1_200

TAVILY_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class SearchHit:
    title: str
    url: str
    snippet: str
    #: When the source was published or last updated (``YYYY-MM-DD``), if the provider knows.
    published: str | None = None


@dataclass(frozen=True)
class SearchResults:
    hits: list[SearchHit]
    answer: str | None = None


class SearchProvider(Protocol):
    """A web search backend. Raises on failure; no hits means no results. ``safe`` asks for
    safe-rated results, where the backend can filter."""

    name: str

    async def search(self, query: str, *, safe: bool) -> SearchResults: ...


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _day(value: object) -> str | None:
    text = _text(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


class TavilyProvider(SearchProvider):
    """Tavily's search API (``search_depth=basic``: one credit per query), with its
    LLM-written answer to the query (``include_answer``)."""

    name = "tavily"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def search(self, query: str, *, safe: bool) -> SearchResults:
        response = await self._client.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "query": query,
                "max_results": MAX_RESULTS,
                "search_depth": "basic",
                "include_answer": "advanced",
                "include_published_date": True,
                "safe_search": safe,
            },
        )
        response.raise_for_status()
        body = response.json()
        hits = [
            SearchHit(
                title=_text(r.get("title")),
                url=r["url"],
                snippet=_text(r.get("content")),
                published=_day(r.get("published_date")),
            )
            for r in body.get("results") or []
            if isinstance(r.get("url"), str) and r["url"]
        ]
        return SearchResults(hits=hits, answer=_text(body.get("answer")).strip() or None)


#: ddgs backends whose request carries the safesearch setting (ddgs 9.16:
#: ``ddgs/engines/{startpage,brave,mojeek}.py``). Its ``duckduckgo`` text engine ignores it.
SAFE_BACKENDS = "startpage,brave,mojeek"
ANY_BACKENDS = "duckduckgo,startpage"


class DdgsProvider(SearchProvider):
    name = "ddgs"

    def __init__(self, backend: str = ANY_BACKENDS, safe_backend: str = SAFE_BACKENDS) -> None:
        self._backend = backend
        self._safe_backend = safe_backend

    def _search_sync(self, query: str, safe: bool) -> SearchResults:
        try:
            rows = DDGS(timeout=8).text(
                query,
                max_results=MAX_RESULTS,
                backend=self._safe_backend if safe else self._backend,
                safesearch="on" if safe else "off",
            )
        except DDGSException as exc:
            if str(exc) == "No results found.":
                return SearchResults(hits=[])
            raise
        return SearchResults(
            hits=[
                SearchHit(title=_text(r.get("title")), url=r["href"], snippet=_text(r.get("body")))
                for r in rows
                if isinstance(r.get("href"), str) and r["href"]
            ]
        )

    async def search(self, query: str, *, safe: bool) -> SearchResults:
        # ddgs is synchronous (threaded HTTP); keep it off the event loop.
        return await asyncio.to_thread(self._search_sync, query, safe)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_results(query: str, results: SearchResults) -> str:
    lines = [f'Web results for "{query}":']
    if results.answer:
        lines.append(f"Answer, from the sources below: {_clip(results.answer, MAX_ANSWER)}")
        lines.append("Sources:")
    for i, hit in enumerate(results.hits, start=1):
        dated = f"published {hit.published}" if hit.published else "date unknown"
        lines.append(f"{i}. {_clip(hit.title, 120) or hit.url} — <{hit.url}> ({dated})")
        if hit.snippet:
            lines.append(f"   {_clip(hit.snippet, MAX_SNIPPET)}")
    lines.append(
        "Answer only from these results, never state a date that isn't shown here, and end "
        "your reply with the links you used, written as <url>."
    )
    return "\n".join(lines)


class WebSearchSkill(Skill[WebSearchArgs]):
    name = "web_search"
    description = "Search the web."
    args_model = WebSearchArgs

    def __init__(self, providers: Sequence[SearchProvider]) -> None:
        if not providers:
            raise ValueError("WebSearchSkill needs at least one provider")
        self._providers = tuple(providers)

    async def run(self, args: WebSearchArgs, ctx: SkillContext) -> SkillResult:
        query = args.query.strip()
        if not query:
            raise InvalidInput("There's nothing to search for.")
        failures = 0
        for provider in self._providers:
            try:
                results = await provider.search(query, safe=not ctx.allows_explicit)
            except (httpx.HTTPError, DDGSException, KeyError, ValueError) as exc:
                failures += 1
                logger.warning("web_search: %s failed: %s", provider.name, type(exc).__name__)
                continue
            if results.hits:
                logger.debug(
                    "web_search: %s answered with %d hits (answer: %s)",
                    provider.name,
                    len(results.hits),
                    results.answer is not None,
                )
                return SkillResult.message(format_results(query, results))
        if failures == len(self._providers):
            raise UpstreamUnavailable("Web search isn't reachable right now.")
        raise EmptyResult(f'The web search for "{query}" found nothing.')
