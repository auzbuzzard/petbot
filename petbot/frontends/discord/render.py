"""Render neutral :class:`SkillResult` values into Discord messages.

This is the *only* place neutral results become Discord types. The pure helpers
(:func:`to_embed`, :func:`chunk_text`) are unit-tested without a gateway; the
async :func:`respond` wires them to an interaction.
"""

from __future__ import annotations

import discord

from petbot.core.skills.context import EmbedSpec, SkillResult
from petbot.core.text import chunk_text

#: Discord's hard limit on message content length.
DISCORD_MAX_TEXT = 2000


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


async def respond(interaction: discord.Interaction, result: SkillResult) -> None:
    """Send ``result`` as a reply to a (deferred) slash-command interaction.

    Expected failures are rendered as a plain message; successes send the text
    (chunked) and, on the first message, the embed.
    """
    if result.is_error:
        await _send(interaction, content=result.error)
        return

    embed = to_embed(result.embed) if result.embed is not None else None
    chunks = chunk_text(result.text or "", limit=DISCORD_MAX_TEXT)

    if not chunks:
        await _send(interaction, content=None, embed=embed)
        return

    for index, chunk in enumerate(chunks):
        await _send(interaction, content=chunk, embed=embed if index == 0 else None)


async def _send(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
) -> None:
    # After a defer(), the only way to reply is the followup webhook. The
    # branches keep the call matched to a concrete `send` overload.
    if content is not None and embed is not None:
        await interaction.followup.send(content=content, embed=embed)
    elif embed is not None:
        await interaction.followup.send(embed=embed)
    elif content is not None:
        await interaction.followup.send(content=content)
