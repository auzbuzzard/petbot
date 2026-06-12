"""Render neutral :class:`SkillResult` values into interaction-response JSON.

The HTTP-Interactions counterpart to :mod:`petbot.frontends.discord.render`,
except it emits **raw dicts** (Discord embed/response JSON) rather than
``discord.Embed`` objects — keeping this adapter ``discord``-free and portable.
"""

from __future__ import annotations

import logging
from typing import Any

from petbot.core.skills.context import EmbedSpec, SkillResult
from petbot.frontends.interactions.wire import CHANNEL_MESSAGE_WITH_SOURCE

logger = logging.getLogger(__name__)

#: Discord's hard limit on message content length.
DISCORD_MAX_TEXT = 2000
#: Shown when output exceeds a single message (see :func:`to_response_data`).
_TRUNCATION_NOTICE = "\n... (output truncated; {omitted} more characters)"
#: Sent instead of an empty body, which Discord would reject.
_EMPTY_PLACEHOLDER = "(no output)"


def to_embed_dict(spec: EmbedSpec) -> dict[str, Any]:
    """Convert a neutral :class:`EmbedSpec` into a Discord embed JSON object.

    Declared as one literal so the output structure is obvious at a glance; keys
    whose value is ``None`` are pruned (Discord omits absent fields).
    """
    author: dict[str, Any] | None = None
    if spec.author_name:
        author = {
            "name": spec.author_name,
            "url": spec.author_url or None,
            "icon_url": spec.author_icon_url or None,
        }
        author = {key: value for key, value in author.items() if value is not None}

    embed: dict[str, Any] = {
        "title": spec.title,
        "description": spec.description,
        "url": spec.url,
        "color": spec.color,
        "image": {"url": spec.image_url} if spec.image_url else None,
        "author": author,
    }
    return {key: value for key, value in embed.items() if value is not None}


def _truncate_to_single_message(text: str, *, limit: int = DISCORD_MAX_TEXT) -> str:
    """Fit ``text`` into one message, appending a visible truncation notice.

    A single *immediate* interaction response is one message (Discord's model),
    so output spanning multiple chunks cannot be delivered here. Rather than
    silently dropping the overflow, we keep as much as fits alongside an explicit
    notice. Full multi-message output needs the deferred follow-up path (#35).
    """
    # Reserve worst-case notice width (omitted <= len(text)) so the result is
    # guaranteed to fit within ``limit``.
    reserved = len(_TRUNCATION_NOTICE.format(omitted=len(text)))
    head = text[: max(0, limit - reserved)]
    omitted = len(text) - len(head)
    return head + _TRUNCATION_NOTICE.format(omitted=omitted)


def to_response_data(result: SkillResult) -> dict[str, Any]:
    """Build the ``data`` object of a CHANNEL_MESSAGE_WITH_SOURCE response."""
    if result.is_error:
        return {"content": result.error}

    data: dict[str, Any] = {}
    text = result.text or ""
    if len(text) > DISCORD_MAX_TEXT:
        logger.warning("Interaction output exceeds one message (%d chars); truncating.", len(text))
        data["content"] = _truncate_to_single_message(text)
    elif text:
        data["content"] = text
    if result.embed is not None:
        data["embeds"] = [to_embed_dict(result.embed)]

    if not data:
        # A successful result with neither text nor embed would serialise to an
        # empty message, which Discord rejects. Surface it explicitly.
        logger.warning("Skill returned an empty result; sending a placeholder.")
        data["content"] = _EMPTY_PLACEHOLDER
    return data


def message_response(result: SkillResult) -> dict[str, Any]:
    """Wrap a :class:`SkillResult` as a full interaction response object."""
    return {"type": CHANNEL_MESSAGE_WITH_SOURCE, "data": to_response_data(result)}
