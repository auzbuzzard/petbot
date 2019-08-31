import asyncio
import re

import discord
from discord.ext import commands


class Echo(commands.Cog):
    """
    Echo the string input in specified seconds
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=False)
    async def echo(self, ctx, *, msg: str):
        # print('echoing')
        async with ctx.typing():
        #     print('inside')
            await ctx.send(msg)

    # @echo.error
    # async def echo_error(self, error, ctx):
    #     await ctx.send("{0.message.author.mention} You didn't tell me what to say… :<".format(ctx))
