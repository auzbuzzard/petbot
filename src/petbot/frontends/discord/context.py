"""Build a neutral :class:`SkillContext` from a Discord message or slash interaction.

The one place Discord nouns (channels, members, NSFW flags) map onto the neutral
context — the only direction the dependency rule allows. An @mention and a slash
command map through the twin functions here, so a skill sees them identically.
"""

from __future__ import annotations

import discord

from petbot.domain import Platform, SkillContext, User


def _channel_is_nsfw(
    channel: discord.abc.MessageableChannel | discord.abc.GuildChannel | None,
) -> bool:
    """True if ``channel`` is an age-gated Discord channel. The union covers a
    message's channel and a slash interaction's channel alike; ``is_nsfw`` is read
    defensively because some channel kinds (a DM) don't carry the flag."""
    is_nsfw = getattr(channel, "is_nsfw", None)
    return bool(is_nsfw()) if callable(is_nsfw) else False


def _place_names(
    guild: discord.Guild | None,
    channel: discord.abc.MessageableChannel | discord.abc.GuildChannel | None,
) -> tuple[str | None, str | None]:
    """The ``(server, channel)`` display names, both ``None`` in a DM. ``name`` is read
    defensively because a DM or partial channel/guild carries none."""
    if guild is None:
        return None, None

    def named(obj: object) -> str | None:
        name = getattr(obj, "name", None)
        return name if isinstance(name, str) and name else None

    return named(guild), named(channel)


def build_context(message: discord.Message) -> SkillContext:
    """Map ``message`` onto a :class:`SkillContext`.

    ``allows_explicit`` comes from the channel's NSFW flag; the conversation id is
    the channel (the natural session unit on Discord); the server and channel names
    ground the chat agent in where it is talking.
    """
    author = message.author
    user = User(
        platform=Platform.DISCORD,
        id=str(author.id),
        display_name=author.display_name,
    )
    community, channel = _place_names(getattr(message, "guild", None), message.channel)
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=f"discord:{message.channel.id}",
        allows_explicit=_channel_is_nsfw(message.channel),
        community_name=community,
        channel_name=channel,
    )


def build_interaction_context(interaction: discord.Interaction) -> SkillContext:
    """Map a slash-command ``interaction`` onto a :class:`SkillContext`.

    The interaction twin of :func:`build_context`: same neutral mapping (NSFW flag,
    channel as the conversation id, place names) so a slash command reaches a skill on the
    exact path an @mention does.
    """
    user = User(
        platform=Platform.DISCORD,
        id=str(interaction.user.id),
        display_name=interaction.user.display_name,
    )
    community, channel = _place_names(getattr(interaction, "guild", None), interaction.channel)
    return SkillContext(
        platform=Platform.DISCORD,
        user=user,
        conversation_id=f"discord:{interaction.channel_id}",
        allows_explicit=_channel_is_nsfw(interaction.channel),
        community_name=community,
        channel_name=channel,
    )
