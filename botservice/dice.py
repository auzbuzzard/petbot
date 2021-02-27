import asyncio
import re
from typing import List

import discord
from discord.ext import commands


class Echo(commands.Cog):
    """
    Echo the string input in specified seconds
    """

    def __init__(self, bot):
        self.bot = bot
        self.diceregex = re.compile(r'\b(\d+)(d\d+)\b')

    @commands.command(pass_context=True, no_pm=False)
    async def roll(self, ctx, *dices: List[str]):
        async with ctx.typing():
            

            await ctx.send(msg)

    # @echo.error
    # async def echo_error(self, error, ctx):
    #     await ctx.send("{0.message.author.mention} You didn't tell me what to say… :<".format(ctx))
