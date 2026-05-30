"""A minimal liveness command, used to prove login + slash sync."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands


class PingCog(commands.Cog):
    """Health-check slash command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="ping", description="Check that PetBot is alive.")
    async def ping(self, interaction: discord.Interaction) -> None:
        latency_ms = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🐾 Pong! ({latency_ms}ms)")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PingCog(bot))
