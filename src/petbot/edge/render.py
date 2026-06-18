"""Render neutral :class:`SkillResult` values into Discord messages.

The *only* place neutral results become Discord types. :func:`to_embed` is a pure
mapping (unit-tested without a gateway); :func:`respond` wires it to a channel.
"""

from __future__ import annotations

import discord

from petbot.domain import EmbedSpec, SkillResult
from petbot.edge.text import DISCORD_MAX_TEXT, chunk_text


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


async def respond(channel: discord.abc.Messageable, result: SkillResult) -> None:
    """Send ``result`` to ``channel``.

    Expected failures render as a plain message; successes send the text (chunked)
    and, on the first message, the embed.
    """
    if result.is_error:
        await channel.send(content=result.error)
        return

    embed = to_embed(result.embed) if result.embed is not None else None
    chunks = chunk_text(result.text or "", limit=DISCORD_MAX_TEXT)

    if not chunks:
        # No text: send the embed alone, or nothing if the result is truly empty.
        if embed is not None:
            await channel.send(embed=embed)
        return

    for index, chunk in enumerate(chunks):
        # The embed rides only the first message; pass it only when present so the
        # call matches discord.py's non-optional `embed` overload.
        if embed is not None and index == 0:
            await channel.send(content=chunk, embed=embed)
        else:
            await channel.send(content=chunk)
