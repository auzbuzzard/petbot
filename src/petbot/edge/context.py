"""Build a neutral :class:`SkillContext` from a Discord message or slash interaction.

The one place Discord nouns (channels, members, NSFW flags) map onto the neutral
context — the only direction the dependency rule allows. An @mention and a slash
command map through the twin functions here, so a skill sees them identically.
"""

from __future__ import annotations

import discord

from petbot.domain import Platform, SkillContext, User


def _channel_is_nsfw(channel: object) -> bool:
    """True if ``channel`` is an age-gated Discord channel. Typed ``object`` so it
    serves both a message channel and an interaction channel (DMs lack the flag)."""
    is_nsfw = getattr(channel, "is_nsfw", None)
    return bool(is_nsfw()) if callable(is_nsfw) else False


def build_context(message: discord.Message) -> SkillContext:
    """Map ``message`` onto a :class:`SkillContext`.

    ``allows_explicit`` comes from the channel's NSFW flag; the conversation id is
    the channel (the natural session unit on Discord).
    """
    author = message.author
    user = User(
        platform=Platform.DISCORD,
        id=str(author.id),
        display_name=author.display_name,
    )
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=f"discord:{message.channel.id}",
        allows_explicit=_channel_is_nsfw(message.channel),
    )


def build_interaction_context(interaction: discord.Interaction) -> SkillContext:
    """Map a slash-command ``interaction`` onto a :class:`SkillContext`.

    The interaction twin of :func:`build_context`: same neutral mapping (NSFW flag,
    channel as the conversation id) so a slash command reaches a skill on the exact
    path an @mention does.
    """
    user = User(
        platform=Platform.DISCORD,
        id=str(interaction.user.id),
        display_name=interaction.user.display_name,
    )
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=f"discord:{interaction.channel_id}",
        allows_explicit=_channel_is_nsfw(interaction.channel),
    )
