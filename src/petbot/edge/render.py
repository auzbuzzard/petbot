"""Render neutral :class:`SkillResult` values into Discord messages.

The *only* place neutral results become Discord types. :func:`to_embed` is a pure
mapping (unit-tested without a gateway); :func:`respond` wires it to a channel (the
@mention path) and :func:`respond_interaction` to a slash-command followup. Both
shape the result identically via :func:`_plan`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import discord

from petbot.domain import EmbedSpec, SkillResult
from petbot.edge.text import DISCORD_MAX_TEXT, chunk_text

#: User-facing fallback when the edge can't reach the worker (any transport error).
#: Lives here (the presentation layer) so both the @mention and slash paths share one
#: copy without a bot<->slash import cycle.
WORKER_UNREACHABLE = "uwu I couldn't reach my brain right now — please try again soon."


def to_embed(spec: EmbedSpec) -> discord.Embed:
    """Convert a neutral :class:`EmbedSpec` into a ``discord.Embed``."""
    embed = discord.Embed(
        title=spec.title,
        description=spec.description,
        url=spec.url,
        color=discord.Color(spec.color) if spec.color is not None else discord.Color.default(),
    )
    if spec.image_url:
        embed.set_image(url=spec.image_url)
    if spec.author_name:
        embed.set_author(
            name=spec.author_name,
            url=spec.author_url or None,
            icon_url=spec.author_icon_url or None,
        )
    return embed


def _plan(result: SkillResult) -> list[tuple[str | None, discord.Embed | None]]:
    """The ordered messages a result becomes: an error is one plain message;
    otherwise the text is chunked and the embed rides only the first chunk."""
    if result.is_error:
        return [(result.error, None)]
    embed = to_embed(result.embed) if result.embed is not None else None
    chunks = chunk_text(result.text or "", limit=DISCORD_MAX_TEXT)
    if not chunks:
        # No text: the embed alone, or nothing if the result is truly empty.
        return [(None, embed)] if embed is not None else []
    return [(chunk, embed if index == 0 else None) for index, chunk in enumerate(chunks)]


async def _send(
    sender: Callable[..., Awaitable[object]],
    content: str | None,
    embed: discord.Embed | None,
) -> None:
    # Pass `embed` only when present so the call matches discord.py's non-optional
    # `embed` overload (a None embed must never reach the gateway).
    if embed is None:
        await sender(content=content)
    elif content is None:
        await sender(embed=embed)
    else:
        await sender(content=content, embed=embed)


async def respond(channel: discord.abc.Messageable, result: SkillResult) -> None:
    """Send ``result`` to ``channel`` (the @mention path).

    Expected failures render as a plain message; successes send the text (chunked)
    and, on the first message, the embed.
    """
    for content, embed in _plan(result):
        await _send(channel.send, content, embed)


async def respond_interaction(interaction: discord.Interaction, result: SkillResult) -> None:
    """Send ``result`` as the followup to an already-deferred slash ``interaction``.

    The slash output port: the same :func:`_plan` shaping as :func:`respond`, emitted
    as ``followup.send`` (the caller has already deferred the interaction response).
    """
    for content, embed in _plan(result):
        await _send(interaction.followup.send, content, embed)
