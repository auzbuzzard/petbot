"""Render neutral :class:`SkillResult` values into interaction-response JSON.

The HTTP-Interactions counterpart to :mod:`petbot.frontends.discord.render`,
except it emits **raw dicts** (Discord embed/response JSON) rather than
``discord.Embed`` objects — keeping this adapter ``discord``-free and portable.
"""

from __future__ import annotations

from typing import Any

from petbot.core.skills.context import EmbedSpec, SkillResult
from petbot.frontends.interactions.wire import CHANNEL_MESSAGE_WITH_SOURCE

#: Discord's hard limit on message content length.
DISCORD_MAX_TEXT = 2000


def to_embed_dict(spec: EmbedSpec) -> dict[str, Any]:
    """Convert a neutral :class:`EmbedSpec` into a Discord embed JSON object."""
    embed: dict[str, Any] = {}
    if spec.title is not None:
        embed["title"] = spec.title
    if spec.description is not None:
        embed["description"] = spec.description
    if spec.url is not None:
        embed["url"] = spec.url
    if spec.color is not None:
        embed["color"] = spec.color
    if spec.image_url:
        embed["image"] = {"url": spec.image_url}
    if spec.author_name:
        author: dict[str, Any] = {"name": spec.author_name}
        if spec.author_url:
            author["url"] = spec.author_url
        if spec.author_icon_url:
            author["icon_url"] = spec.author_icon_url
        embed["author"] = author
    return embed


def chunk_text(text: str, *, limit: int = DISCORD_MAX_TEXT) -> list[str]:
    """Split ``text`` into chunks no longer than ``limit``, preferring newlines.

    Mirrors the gateway adapter's chunker. Never splits mid-line unless a single
    line itself exceeds ``limit``.
    """
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        if len(current) + len(line) > limit:
            chunks.append(current)
            current = line
        else:
            current += line
    if current:
        chunks.append(current)
    return [chunk for chunk in chunks if chunk]


def to_response_data(result: SkillResult) -> dict[str, Any]:
    """Build the ``data`` object of a CHANNEL_MESSAGE_WITH_SOURCE response.

    Expected failures render as plain content. A single immediate response holds
    one message; text longer than the limit keeps only the first chunk for now —
    multi-message output needs the deferred-follow-up path (a documented TODO,
    not yet needed for the stateless skills).
    """
    if result.is_error:
        return {"content": result.error}

    data: dict[str, Any] = {}
    chunks = chunk_text(result.text or "")
    if chunks:
        data["content"] = chunks[0]
    if result.embed is not None:
        data["embeds"] = [to_embed_dict(result.embed)]
    return data


def message_response(result: SkillResult) -> dict[str, Any]:
    """Wrap a :class:`SkillResult` as a full interaction response object."""
    return {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": to_response_data(result)}
