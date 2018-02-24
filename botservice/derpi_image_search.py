import asyncio
import discord
from discord.ext import commands

from capabilities.derpibooru import derpibooru


class DerpiImageSearch:
    """
    Image Search on Derpibooru.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=False)
    async def search(self, ctx, *, search_terms: str):
        image = derpibooru.search(search_terms)

        await self.bot.say("Found image.")
        await self.bot.say("https:" + image.representations['large'])

