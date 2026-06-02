"""``/purge`` — bulk-delete recent messages. A Discord-adapter concern (it acts
on the platform directly), permission-gated, not a neutral skill.

The legacy ``ghost_talk`` (cross-guild impersonation) is intentionally removed.
"""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(
        name="purge", description="Delete the most recent messages in this channel."
    )
    @app_commands.describe(count="How many messages to delete (1-100).")
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.guild_only()
    async def purge(
        self, interaction: discord.Interaction, count: app_commands.Range[int, 1, 100]
    ) -> None:
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "I can only purge messages in a text channel.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await channel.purge(limit=count)
        logger.info(
            "purge: %s deleted %d message(s) in #%s", interaction.user, len(deleted), channel.name
        )
        await interaction.followup.send(f"🧹 Deleted {len(deleted)} message(s).", ephemeral=True)

    @purge.error
    async def purge_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "You need the Manage Messages permission to do that."
        else:
            logger.error("purge failed unexpectedly", exc_info=error)
            message = "Something went wrong running that command."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminCog(bot))
