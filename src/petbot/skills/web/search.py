"""The ``web_search`` skill: ranked providers, first one that answers wins.

Tavily (keyed, built for LLM consumers) runs first; ``ddgs`` (keyless metasearch over
public result pages) is the fallback for a missing key, an exhausted quota, or an outage.
The results come back as a compact numbered list the agent reads and cites from, each with
its publication date when the provider knows it and marked undated when it doesn't, so the
model never has to guess when a snippet was written. Outside an age-gated channel both
providers are asked for safe results (Tavily's ``safe_search``, ddgs's ``safesearch``).
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
#: Per-result snippet cap, in characters.
MAX_SNIPPET = 400

TAVILY_URL = "https://api.tavily.com/search"


@dataclass(frozen=True)
class SearchHit:
    """One search result, provider-neutral."""

    title: str
    url: str
    snippet: str
    #: When the source was published or last updated (``YYYY-MM-DD``), if the provider knows.
    published: str | None = None


class SearchProvider(Protocol):
    """A web search backend. Raises on failure; an empty list means no results. ``safe``
    asks for safe-rated results, where the backend can filter."""

    name: str

    async def search(self, query: str, *, safe: bool) -> list[SearchHit]: ...


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _day(value: object) -> str | None:
    """The ``YYYY-MM-DD`` day of a provider timestamp, or ``None`` if it has none."""
    text = _text(value).strip()
    return text[:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else None


class TavilyProvider(SearchProvider):
    """Tavily's search API (``search_depth=basic``: one credit per query)."""

    name = "tavily"

    def __init__(self, client: httpx.AsyncClient, api_key: str) -> None:
        self._client = client
        self._api_key = api_key

    async def search(self, query: str, *, safe: bool) -> list[SearchHit]:
        response = await self._client.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "query": query,
                "max_results": MAX_RESULTS,
                "search_depth": "basic",
                "include_published_date": True,
                "safe_search": safe,
            },
        )
        response.raise_for_status()
        return [
            SearchHit(
                title=_text(r.get("title")),
                url=r["url"],
                snippet=_text(r.get("content")),
                published=_day(r.get("published_date")),
            )
            for r in response.json().get("results") or []
            if isinstance(r.get("url"), str) and r["url"]
        ]


class DdgsProvider(SearchProvider):
    """Keyless metasearch via ``ddgs``, pinned to the engines that answer cloud IPs."""

    name = "ddgs"

    def __init__(self, backend: str = "duckduckgo,startpage") -> None:
        self._backend = backend

    def _search_sync(self, query: str, safe: bool) -> list[SearchHit]:
        try:
            rows = DDGS(timeout=8).text(
                query,
                max_results=MAX_RESULTS,
                backend=self._backend,
                safesearch="on" if safe else "off",
            )
        except DDGSException as exc:
            # ddgs raises this exact message when every engine answered with nothing; any
            # engine error replaces it, so it reliably means "no results", not an outage.
            if str(exc) == "No results found.":
                return []
            raise
        return [
            SearchHit(title=_text(r.get("title")), url=r["href"], snippet=_text(r.get("body")))
            for r in rows
            if isinstance(r.get("href"), str) and r["href"]
        ]

    async def search(self, query: str, *, safe: bool) -> list[SearchHit]:
        # ddgs is synchronous (threaded HTTP); keep it off the event loop.
        return await asyncio.to_thread(self._search_sync, query, safe)


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def format_hits(query: str, hits: Sequence[SearchHit]) -> str:
    """The numbered result list handed to the model, each result dated or marked undated,
    closed by how to use them: a small model follows an instruction next to the material
    far more reliably than one in its system prompt."""
    lines = [f'Web results for "{query}":']
    for i, hit in enumerate(hits, start=1):
        dated = f"published {hit.published}" if hit.published else "date unknown"
        lines.append(f"{i}. {_clip(hit.title, 120) or hit.url} — <{hit.url}> ({dated})")
        if hit.snippet:
            lines.append(f"   {_clip(hit.snippet, MAX_SNIPPET)}")
    lines.append(
        "These are short excerpts. Never state a date that isn't shown here or in a page you "
        "read. If the question is about the latest or current state of something, read the "
        "most authoritative source above with web_fetch before answering. Answer only from "
        "what you read, and end your reply with the links you used, written as <url>."
    )
    return "\n".join(lines)


class WebSearchSkill(Skill[WebSearchArgs]):
    """Search the web through the first provider that answers."""

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
                hits = await provider.search(query, safe=not ctx.allows_explicit)
            except (httpx.HTTPError, DDGSException, KeyError, ValueError) as exc:
                # A quota/outage/parse failure on one provider falls through to the next.
                failures += 1
                logger.warning("web_search: %s failed: %s", provider.name, type(exc).__name__)
                continue
            if hits:
                logger.debug("web_search: %s answered with %d hits", provider.name, len(hits))
                return SkillResult.message(format_hits(query, hits))
        if failures == len(self._providers):
            raise UpstreamUnavailable("Web search isn't reachable right now.")
        raise EmptyResult(f'The web search for "{query}" found nothing.')
