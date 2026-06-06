"""``/math`` — evaluate an expression via the neutral :class:`MathSkill`."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from petbot.core.skills.math_skill import MathSkill
from petbot.frontends.discord import render
from petbot.frontends.discord.context import build_context

logger = logging.getLogger(__name__)


class MathCog(commands.Cog):
    def __init__(self, bot: commands.Bot, skill: MathSkill) -> None:
        self.bot = bot
        self.skill = skill

    @app_commands.command(name="math", description="Evaluate a mathematical expression.")
    @app_commands.describe(expression="The expression to evaluate, e.g. 2 * 21")
    async def math(self, interaction: discord.Interaction, expression: str) -> None:
        await interaction.response.defer(thinking=True)
        logger.debug("/math invoked by %s: %r", interaction.user, expression)
        ctx = build_context(interaction)
        result = await self.skill.run({"expression": expression}, ctx)
        await render.respond(interaction, result)
