"""``/derpi`` and ``/e621`` — booru search via the neutral booru skills.

Both slash commands are marked ``nsfw=True`` at the Discord layer; explicit
*results* are additionally gated inside the skill on the channel's NSFW flag
(surfaced through ``ctx.capabilities.allows_explicit``).
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.frontends.discord import render
from petbot.frontends.discord.context import build_context


class BooruCog(commands.Cog):
    def __init__(self, bot: commands.Bot, derpi: DerpiSkill, e621: E621Skill) -> None:
        self.bot = bot
        self._derpi = derpi
        self._e621 = e621

    @app_commands.command(name="derpi", description="Search Derpibooru for an image.")
    @app_commands.describe(tags="Comma-separated tags; add --e in NSFW channels for explicit.")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def derpi(self, interaction: discord.Interaction, tags: str) -> None:
        await interaction.response.defer(thinking=True)
        ctx = build_context(interaction)
        result = await self._derpi.run({"tags": tags}, ctx)
        await render.respond(interaction, result)

    @app_commands.command(name="e621", description="Search e621/e926 for an image.")
    @app_commands.describe(tags="Comma-separated tags; add --e in NSFW channels for explicit.")
    @app_commands.allowed_installs(guilds=True, users=False)
    async def e621(self, interaction: discord.Interaction, tags: str) -> None:
        await interaction.response.defer(thinking=True)
        ctx = build_context(interaction)
        result = await self._e621.run({"tags": tags}, ctx)
        await render.respond(interaction, result)
