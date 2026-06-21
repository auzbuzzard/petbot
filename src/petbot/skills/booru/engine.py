"""The shared search engine: one async function every provider flows through.

The site-specific skill builds a neutral :class:`SearchRequest`; the engine asks
the provider to serialize it, sends it on the injected ``httpx.AsyncClient``, and
reads the body on *every* status. Error handling is layered: the site's own
message (from the body) wins for UX; a non-2xx status with no recognizable error
body still raises rather than silently looking like "no results".
"""

from __future__ import annotations

import logging

import httpx

from petbot.domain import SkillResult
from petbot.skills.booru.base import BooruProvider
from petbot.skills.booru.errors import SiteFailureStatusError
from petbot.skills.booru.render import render
from petbot.skills.booru.types import SearchRequest

logger = logging.getLogger(__name__)


def _site_rejected(site: str, reason: str) -> str:
    return f"uwu I couldn't do that. {site} says: {reason}"


def _site_http_error(site: str, status: int) -> str:
    return f"uwu {site} returned an error (HTTP {status})."


def _site_unreadable(site: str) -> str:
    return f"uwu {site} sent a response I couldn't read."


async def run_search(
    provider: BooruProvider,
    client: httpx.AsyncClient,
    search: SearchRequest,
) -> SkillResult:
    """Send the search, surface any site/HTTP error, then render the first result."""
    # Logged from the neutral SearchRequest, never the wire request — the latter
    # can carry an api_key/User-Agent, and secrets must never reach the logs.
    logger.debug(
        "%s search: tags=%s safe_only=%s sort=%s",
        provider.name,
        search.tags,
        search.safe_only,
        search.sort,
    )
    request = provider.build_request(client, search)
    response = await client.send(request)
    logger.debug("%s responded HTTP %d", provider.name, response.status_code)
    body = _json_body(response)

    # Each failure below is signalled by *raising* — the exception is the error
    # report. We deliberately don't log here: that would double-log (the caller
    # that handles the exception is the right place to decide level + traceback).

    # 1. The site's own error message wins (best UX) — when the body decoded.
    if body is not None and (reason := provider.error(body)) is not None:
        raise SiteFailureStatusError(
            site_message=reason,
            print_message=_site_rejected(provider.name, reason),
        )
    # 2. Any other non-2xx is still an error, even with no recognizable error body.
    if response.status_code >= 400:
        raise SiteFailureStatusError(
            site_message=f"HTTP {response.status_code}",
            print_message=_site_http_error(provider.name, response.status_code),
        )
    # 3. A 2xx we couldn't decode is an anomaly — surface it, don't fake "no results".
    if body is None:
        raise SiteFailureStatusError(
            site_message="non-JSON response",
            print_message=_site_unreadable(provider.name),
        )

    return render(provider.parse(body), request=search)


def _json_body(response: httpx.Response) -> object | None:
    """Decoded JSON body, or ``None`` if it isn't JSON. A ``None`` body is never
    swallowed — the caller always turns it into a raised error (never "no results")."""
    try:
        body: object = response.json()
    except ValueError:
        return None
    return body
