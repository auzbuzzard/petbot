"""Build a neutral :class:`SkillContext` from a Discord message.

The one place Discord nouns (channels, members, NSFW flags) map onto the neutral
context — the only direction the dependency rule allows.
"""

from __future__ import annotations

import discord

from petbot.domain import Platform, SkillContext, User


def _channel_is_nsfw(channel: discord.abc.MessageableChannel) -> bool:
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
