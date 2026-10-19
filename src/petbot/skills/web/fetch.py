"""The ``web_fetch`` skill: read one page as markdown text.

Every hop (the URL and each redirect) goes through pydantic-ai's SSRF guard: the host is
resolved and refused if any address is private, loopback, link-local or cloud metadata,
then dialed by IP with the original Host/SNI. That matters on Lambda, where the runtime API
listens on localhost. pydantic-ai's own ``safe_download`` reads the whole body into
memory, so the request loop is ours: it streams with a byte cap and an overall deadline.
The ``_ssrf`` helpers are private, but the dependency is pinned below its next major and
the guard is covered by tests.

An HTML page is reduced to its main content (``trafilatura``) before it reaches the model:
a whole-page conversion is mostly navigation, link markup and embedded schema JSON, which
crowds the article out of the text cap and leaves the model reasoning over boilerplate.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urlparse

import httpx
import trafilatura
from pydantic_ai._ssrf import build_url_with_ip, resolve_redirect_url, validate_and_resolve_url

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
#: Download cap, in bytes: a long article's HTML fits; a video or ISO is cut off early.
MAX_BYTES = 2_000_000
MAX_REDIRECTS = 5

_TEXT_TYPES = ("text/", "application/json", "application/xhtml+xml", "application/xml")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_BLANK_LINES_RE = re.compile(r"\n{3,}")


class _TooLarge(Exception):
    pass


async def _read_capped(response: httpx.Response) -> bytes:
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise _TooLarge
    return bytes(body)


async def fetch_page(
    client: httpx.AsyncClient, url: str, headers: dict[str, str]
) -> tuple[str, str, bytes | None]:
    """``(final_url, media_type, body)`` for ``url``, SSRF-checked on every hop. ``body`` is
    ``None`` for a non-text response, which is never downloaded.

    Raises ``ValueError`` for a refused address or too many redirects, ``httpx`` errors for
    transport/HTTP failures, and :class:`_TooLarge` past :data:`MAX_BYTES`.
    """
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        resolved = await validate_and_resolve_url(current, allow_local=False)
        extensions = {"sni_hostname": resolved.hostname} if resolved.is_https else {}
        request = client.build_request(
            "GET",
            build_url_with_ip(resolved),
            headers={**headers, "Host": resolved.hostname},
            extensions=extensions,
        )
        response = await client.send(request, stream=True, follow_redirects=False)
        try:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("redirect without a Location header")
                current = resolve_redirect_url(current, location)
                continue
            response.raise_for_status()
            media_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type and not media_type.startswith(_TEXT_TYPES):
                return current, media_type, None
            return current, media_type, await _read_capped(response)
        finally:
            await response.aclose()
    raise ValueError("too many redirects")


def to_markdown(media_type: str, text: str, url: str) -> tuple[str, str]:
    """``(title, content)`` of a fetched page: an HTML page's main content as markdown,
    any other text as-is. CPU-bound; call it off the event loop.

    A page with no recognisable main content (an app shell, a link hub) falls back to the
    page's visible text, still without markup.
    """
    title = ""
    if not media_type or media_type in ("text/html", "application/xhtml+xml"):
        match = _TITLE_RE.search(text)
        title = " ".join(match.group(1).split()) if match else ""
        main = trafilatura.extract(
            text,
            url=url,
            output_format="markdown",
            include_links=False,
            include_images=False,
            include_tables=True,
            include_comments=False,
        )
        text = main or trafilatura.html2txt(text)
    text = _BLANK_LINES_RE.sub("\n\n", text).strip()
    if len(text) > MAX_CONTENT:
        text = text[:MAX_CONTENT] + "\n\n[Content truncated]"
    return title, text


class WebFetchSkill(Skill[WebFetchArgs]):
    """Fetch a public web page and return its text."""

    name = "web_fetch"
    description = "Read a web page."
    args_model = WebFetchArgs

    def __init__(
        self, client: httpx.AsyncClient, user_agent: str, *, deadline: float = 12.0
    ) -> None:
        self._client = client
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/markdown, text/html;q=0.9, */*;q=0.8",
        }
        self._deadline = deadline

    async def run(self, args: WebFetchArgs, ctx: SkillContext) -> SkillResult:
        url = args.url.strip()
        if urlparse(url).scheme not in ("http", "https"):
            raise InvalidInput("That doesn't look like a web link.")
        try:
            async with asyncio.timeout(self._deadline):
                final_url, media_type, body = await fetch_page(self._client, url, self._headers)
        except _TooLarge as exc:
            raise InvalidInput("That page is too big for me to read.") from exc
        except (ValueError, httpx.HTTPError, TimeoutError) as exc:
            logger.debug("web_fetch: %s", type(exc).__name__)
            raise UpstreamUnavailable("That page couldn't be opened.") from exc
        if body is None:
            raise InvalidInput(f"That link is a {media_type} file, not a readable page.")
        title, content = await asyncio.to_thread(
            to_markdown, media_type, body.decode("utf-8", errors="replace"), final_url
        )
        heading = f"Title: {title}\n" if title else ""
        return SkillResult.message(
            f"Page <{final_url}>\n{heading}\n{content}\n\n"
            f"Answer from this page and cite it as <{final_url}>."
        )
