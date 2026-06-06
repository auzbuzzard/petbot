"""``/music play|skip|stop|queue|volume`` — voice playback.

The cog builds a per-interaction :class:`DiscordVoicePort` bound to the invoking
member's guild, then delegates all queue/skip-vote logic to the shared neutral
:class:`MusicSkill`.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from petbot.core.skills.music_skill import MusicSkill
from petbot.frontends.discord import render
from petbot.frontends.discord.context import build_context
from petbot.frontends.discord.voice import DiscordVoicePort

logger = logging.getLogger(__name__)


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot, skill: MusicSkill) -> None:
        self.bot = bot
        self.skill = skill

    music = app_commands.Group(name="music", description="Play and manage audio.")

    def _voice_port(self, interaction: discord.Interaction) -> DiscordVoicePort | None:
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return None
        return DiscordVoicePort(guild=guild, member=member)

    async def _dispatch(self, interaction: discord.Interaction, args: dict[str, object]) -> None:
        await interaction.response.defer(thinking=True)
        logger.debug("/music %s invoked by %s", args.get("action"), interaction.user)
        voice = self._voice_port(interaction)
        if voice is None:
            await interaction.followup.send("Music only works in a server voice channel.")
            return
        ctx = build_context(interaction, voice=voice)
        result = await self.skill.run(args, ctx)
        await render.respond(interaction, result)

    @music.command(name="play", description="Play a URL or search term (queues if busy).")
    @app_commands.describe(query="A URL or search term to play.")
    async def play(self, interaction: discord.Interaction, query: str) -> None:
        await self._dispatch(interaction, {"action": "play", "query": query})

    @music.command(name="skip", description="Vote to skip the current track.")
    async def skip(self, interaction: discord.Interaction) -> None:
        await self._dispatch(interaction, {"action": "skip"})

    @music.command(name="stop", description="Stop playback and clear the queue.")
    async def stop(self, interaction: discord.Interaction) -> None:
        await self._dispatch(interaction, {"action": "stop"})

    @music.command(name="queue", description="Show the current queue.")
    async def queue(self, interaction: discord.Interaction) -> None:
        await self._dispatch(interaction, {"action": "queue"})

    @music.command(name="volume", description="Set playback volume (0-100).")
    @app_commands.describe(level="Volume percentage from 0 to 100.")
    async def volume(self, interaction: discord.Interaction, level: int) -> None:
        await self._dispatch(interaction, {"action": "volume", "level": level})
