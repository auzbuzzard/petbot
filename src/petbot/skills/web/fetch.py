"""The ``web_fetch`` skill: read one page as markdown text.

Delegates the HTTP to pydantic-ai's local web-fetch tool for its SSRF guard: private,
loopback and link-local addresses are refused, which matters on Lambda, where the runtime
API listens on localhost.
"""

from __future__ import annotations

import logging

from pydantic_ai.common_tools.web_fetch import WebFetchLocalTool
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import BinaryContent

from petbot.domain import (
    InvalidInput,
    Skill,
    SkillContext,
    SkillResult,
    UpstreamUnavailable,
)
from petbot.types import WebFetchArgs

logger = logging.getLogger(__name__)

#: Page text cap, in characters (~2K tokens): the gist of an article, not the whole site.
MAX_CONTENT = 8_000


class WebFetchSkill(Skill[WebFetchArgs]):
    """Fetch a public web page and return its text."""

    name = "web_fetch"
    description = "Read a web page."
    args_model = WebFetchArgs

    def __init__(self, user_agent: str, *, timeout: int = 15) -> None:
        self._fetch = WebFetchLocalTool(
            max_content_length=MAX_CONTENT,
            allow_local_urls=False,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )

    async def run(self, args: WebFetchArgs, ctx: SkillContext) -> SkillResult:
        url = args.url.strip()
        if not url.startswith(("http://", "https://")):
            raise InvalidInput("That doesn't look like a web link.")
        try:
            page = await self._fetch(url)
        except ModelRetry as exc:
            logger.debug("web_fetch: %s", exc)
            raise UpstreamUnavailable("That page couldn't be opened.") from exc
        if isinstance(page, BinaryContent):
            raise InvalidInput(f"That link is a {page.media_type} file, not a readable page.")
        title = f"Title: {page['title']}\n" if page["title"] else ""
        return SkillResult.message(f"Page <{page['url']}>\n{title}\n{page['content']}")
