from discord.ext import commands

from capabilities.boorus import booru


class ImageSearch:
    """
    Image Search on Derpibooru.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='derpi', pass_context=True, no_pm=False)
    async def search_derpi(self, ctx, *, inputs: str):
        await self.bot.send_typing(ctx.message.channel)

        greeter, embed = booru.search(site=booru.Sites.derpibooru, ctx=ctx, messages=inputs)
        await self.bot.say(content=greeter, embed=embed)

    @commands.command(name='e621', pass_context=True, no_pm=False)
    async def search_e621(self, ctx, *, inputs: str):
        await self.bot.send_typing(ctx.message.channel)

        greeter, embed = booru.search(site=booru.Sites.e621, ctx=ctx, messages=inputs)
        await self.bot.say(content=greeter, embed=embed)

