"""Resolve a :class:`~petbot.domain.ports.VoicePort` from a request context.

The music worker's gateway caches guild/member/voice state; this provider reads
that cache to bind a :class:`DiscordVoicePort` to the invoking member's current
voice channel. The conversation id is ``discord:{text_channel_id}``; the guild is
that channel's guild, the member is ``ctx.user.id`` within it.
"""

from __future__ import annotations

import logging

import discord

from petbot.domain import SkillContext, VoicePort
from petbot.workers.music.voice import DiscordVoicePort

logger = logging.getLogger(__name__)


def _channel_id(conversation_id: str) -> int | None:
    _, _, raw = conversation_id.rpartition(":")
    return int(raw) if raw.isdigit() else None


class DiscordVoiceProvider:
    """Binds a voice port to the invoking member, using the gateway's cache."""

    def __init__(self, bot: discord.Client) -> None:
        self._bot = bot

    def for_context(self, ctx: SkillContext) -> VoicePort | None:
        channel_id = _channel_id(ctx.conversation_id)
        if channel_id is None:
            return None
        channel = self._bot.get_channel(channel_id)
        guild = getattr(channel, "guild", None)
        if not isinstance(guild, discord.Guild):
            return None
        member = guild.get_member(int(ctx.user.id))
        if member is None or member.voice is None:
            logger.debug("music: %s is not in a voice channel", ctx.user.id)
            return None
        return DiscordVoicePort(guild=guild, member=member)
