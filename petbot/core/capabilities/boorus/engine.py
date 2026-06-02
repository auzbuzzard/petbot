"""The shared search engine: one async function every provider flows through.

The site-specific skill builds a neutral :class:`SearchRequest`; the engine asks
the provider to serialize it, sends it on the injected ``httpx.AsyncClient``, and
reads the body on *every* status. Error handling is layered: the site's own
message (from the body) wins for UX; a non-2xx status with no recognizable error
body still raises rather than silently looking like "no results".
"""

from __future__ import annotations

import httpx

from petbot.core.capabilities.boorus.base import BooruProvider
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.render import render
from petbot.core.capabilities.boorus.types import SearchRequest
from petbot.core.skills.context import SkillResult


async def run_search(
    provider: BooruProvider,
    client: httpx.AsyncClient,
    search: SearchRequest,
    *,
    author: str,
) -> SkillResult:
    """Send the search, surface any site/HTTP error, then render the first result."""
    request = provider.build_request(client, search)
    response = await client.send(request)
    body = _decode(response)

    if body is not None and (reason := provider.error(body)) is not None:
        raise SiteFailureStatusError(
            site_message=reason,
            print_message=f"uwu I couldn't do that. {provider.name} says: {reason}",
        )
    if response.status_code >= 400:
        raise SiteFailureStatusError(
            site_message=f"HTTP {response.status_code}",
            print_message=f"uwu {provider.name} returned an error (HTTP {response.status_code}).",
        )

    post = provider.parse(body) if body is not None else None
    return render(post, request=search, author=author)


def _decode(response: httpx.Response) -> object | None:
    """JSON body, or ``None`` if the response is not JSON (e.g. a CDN error page)."""
    try:
        body: object = response.json()
    except ValueError:
        return None
    return body
