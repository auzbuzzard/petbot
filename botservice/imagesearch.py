import asyncio
import discord
from discord.ext import commands

from capabilities.derpibooru import derpibooru
from capabilities.e621 import e621


class ImageSearch:
    """
    Image Search on Derpibooru.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='derpi', pass_context=True, no_pm=False)
    async def search_derpi(self, ctx, *, inputs: str):

        args, tags = derpibooru.parse_args(inputs)

        image, count = derpibooru.search(args, tags)

        if image is not None:
            await self.bot.say(
                "Found image for: {} (from {} results) \n".format(tags, count) +
                "https:{}".format(image.representations['large'])
            )
        else:
            await self.bot.say("Can't find images for: {}. :<".format(tags))

    @commands.command(disabled=True, name='e621', pass_context=True, no_pm=False)
    async def search_e621(self, ctx, *, inputs: str):

        args, tags = derpibooru.parse_args(inputs)

        image, count = derpibooru.search(args, tags)

        if image is not None:
            await self.bot.say("Found image for: {} (from {} results)".format(tags, count))
            await self.bot.say("https:" + image.representations['large'])
        else:
            await self.bot.say("Can't find images for: {}. :<".format(tags))