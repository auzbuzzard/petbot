import asyncio
import discord
from discord.ext import commands

import numexpr


class Math:
    """
    Commands for simple math functions
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=False)
    async def math(self, ctx, *, msg: str):
        try:
            result = numexpr.evaluate(msg).item()
            await self.bot.say(
                "```py\n>>>\t{}\n<<<\t{}\n```".format(msg, result)
            )
        except Exception as e:
            await self.bot.say(
                "```py\n>>>\t{}\n<<<\t{}\n```".format(msg, e)
            )

    @commands.command(pass_context=True, no_pm=False)
    async def roll_dice(self, ctx, *, msg: str):
        pass
