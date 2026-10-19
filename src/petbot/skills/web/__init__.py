"""The web skill package: ``web_search`` and ``web_fetch``.

The entry-point factories read :class:`~petbot.skills.web.settings.WebSettings`: with a
Tavily key the search runs Tavily first and ``ddgs`` as the fallback; without one, ``ddgs``
alone.
"""

from __future__ import annotations

import httpx

from petbot.skills.web.fetch import WebFetchSkill
from petbot.skills.web.search import (
    DdgsProvider,
    SearchProvider,
    TavilyProvider,
    WebSearchSkill,
)
from petbot.skills.web.settings import WebSettings

__all__ = ["WebFetchSkill", "WebSearchSkill", "build_fetch", "build_search"]

_client: httpx.AsyncClient | None = None


def _shared_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=15.0)
    return _client


def build_search() -> WebSearchSkill:
    """Build the search skill from the environment."""
    settings = WebSettings()
    providers: list[SearchProvider] = []
    if settings.tavily_api_key is not None:
        providers.append(TavilyProvider(_shared_client(), settings.tavily_api_key))
    providers.append(DdgsProvider())
    return WebSearchSkill(providers)


def build_fetch() -> WebFetchSkill:
    """Build the page-fetch skill from the environment."""
    return WebFetchSkill(WebSettings().user_agent)
