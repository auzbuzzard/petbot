"""The shared search engine: one async function every provider flows through.

The site-specific skill builds the request (it knows its own ``Sort`` type) and
hands the resulting context manager here. We read the body on *every* status,
check for a site error first (so the real message survives), then decode the
success body and render it.
"""

from __future__ import annotations

from petbot.core.capabilities.boorus.base import BooruProvider
from petbot.core.capabilities.boorus.errors import SiteFailureStatusError
from petbot.core.capabilities.boorus.http import HttpResponseContext
from petbot.core.capabilities.boorus.render import render
from petbot.core.capabilities.boorus.types import SearchRequest
from petbot.core.skills.context import SkillResult


async def run_search(
    provider: BooruProvider,
    response: HttpResponseContext,
    search: SearchRequest,
    *,
    author: str,
) -> SkillResult:
    """Read the response, surface any site error, then render the first result."""
    async with response as resp:
        body = await resp.json(content_type=None)  # never raise_for_status

    reason = provider.error_model.model_validate(body).reason()
    if reason is not None:
        raise SiteFailureStatusError(
            site_message=reason,
            print_message=f"uwu I couldn't do that. {provider.name} says: {reason}",
        )

    post = provider.response_model.model_validate(body).to_post()
    return render(post, request=search, author=author)
