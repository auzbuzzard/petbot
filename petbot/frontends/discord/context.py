"""Build a neutral :class:`SkillContext` from a Discord interaction.

This is where Discord nouns (channels, members, NSFW flags) are mapped onto the
core's capability flags — the one direction the dependency rule allows.
"""

from __future__ import annotations

import discord

from petbot.core.skills.context import Capabilities, Platform, SkillContext, User
from petbot.core.skills.ports import VoicePort


def _channel_is_nsfw(interaction: discord.Interaction) -> bool:
    channel = interaction.channel
    is_nsfw = getattr(channel, "is_nsfw", None)
    return bool(is_nsfw()) if callable(is_nsfw) else False


def build_context(
    interaction: discord.Interaction,
    *,
    voice: VoicePort | None = None,
) -> SkillContext:
    """Map ``interaction`` onto a :class:`SkillContext`.

    ``allows_explicit`` comes from the channel's NSFW flag; ``supports_voice`` is
    true exactly when a :class:`VoicePort` was supplied.
    """
    discord_user = interaction.user
    user = User(
        platform=Platform.DISCORD,
        id=str(discord_user.id),
        display_name=discord_user.display_name,
    )
    capabilities = Capabilities(
        allows_explicit=_channel_is_nsfw(interaction),
        supports_voice=voice is not None,
        supports_rich_embeds=True,
        max_text_length=2000,
    )
    # Sessions (Phase B) key off a neutral conversation id; the channel is the
    # natural unit on Discord.
    conversation_id = f"discord:{interaction.channel_id}"
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=conversation_id,
        capabilities=capabilities,
        voice=voice,
    )
