from discord.ext import commands

from capabilities.boorus import booru, errors


class ImageSearch:
    """
    Image Search on Derpibooru.
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='derpi', pass_context=True, no_pm=False)
    async def search_derpi(self, ctx, *, inputs: str):
        await self.bot.send_typing(ctx.message.channel)

        try:
            greeter, embed = booru.search(site=booru.Sites.derpibooru, ctx=ctx, messages=inputs)
            await self.bot.say(content=greeter, embed=embed)
        except errors.SiteFailureStatusError as e:
            if e.need_code_block:
                await self.bot.say("```py\n{}\n```".format(e.print_message))
            else:
                await self.bot.say(e.print_message)

    @commands.command(name='e621', pass_context=True, no_pm=False)
    async def search_e621(self, ctx, *, inputs: str):
        await self.bot.send_typing(ctx.message.channel)

        try:
            greeter, embed = booru.search(site=booru.Sites.e621, ctx=ctx, messages=inputs)
            await self.bot.say(content=greeter, embed=embed)
        except errors.SiteFailureStatusError as e:
            if e.need_code_block:
                await self.bot.say("```py\n{}\n```".format(e.print_message))
            else:
                await self.bot.say(e.print_message)
