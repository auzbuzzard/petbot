from discord.ext import commands

from capabilities.derpibooru import derpibooru


class DerpiImageSearch:
    """
    Image Search on Derpibooru.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='derpi', pass_context=True, no_pm=False)
    async def search(self, ctx, *, inputs: str):

        args, tags = derpibooru.parse_args(inputs)

        image = derpibooru.search(args, tags)

        if image is not None:
            await self.bot.say("Found image for: {}".format(tags))
            await self.bot.say("https:" + image.representations['large'])
        else:
            await self.bot.say("Can't find images for: {}. :<".format(tags))

