import re

import discord
from discord.ext import commands


class Admin:
    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True, no_pm=True)
    async def delete_bot_message(self, ctx, *, message: str):
        async for msg in self.bot.logs_from(ctx.message.channel, limit=20):
            if msg.author == self.bot.user and msg.content == message:
                print(msg.content)
                await self.bot.delete_message(msg)

    # TODO: Fix counting and also permission check
    @commands.command(pass_context=True, no_pm=False)
    async def delete_bot_message_by_count(self, ctx, *, message: str):
        await self.bot.send_typing(ctx.message.channel)
        try:
            f = re.match(r'\"(?P<server>[^\"]*)\" \"(?P<channel>[^\"]*)\" (?P<limit>[\d]+)', message)

            limit = int(f.group('limit'))

            server = discord.utils.get(self.bot.servers, name=f.group('server'))
            if server is None:
                await self.bot.send_message(ctx.message.channel,
                                            ":< I can't find any channel named \"{0}\""
                                            .format(f.group('server')))
                return
            await self.bot.say('Found server: {}'.format(server.name))

            channel = discord.utils.get(server.channels, name=f.group('channel'))
            if channel is None:
                await self.bot.send_message(ctx.message.channel,
                                            ":< I can't find any channel named \"{0}\" in \"{1}\""
                                            .format(f.group('server'), f.group('channel')))
                return
            await self.bot.say('Found channel: {} in {}'.format(channel.name, server.name))

            async for msg in self.bot.logs_from(channel, limit=limit):
                if msg.author == self.bot.user:
                    await self.bot.delete_message(msg)

            # await self.bot.purge_from(
            #     ctx.message.channel, limit=limit,
            #     check=lambda msg: msg.author == self.bot.user
            # )
        except Exception as e:
            await self.bot.say("```py\n{}\n```".format(e))

    @commands.command(pass_context=True, no_pm=True)
    async def echo_message(self, ctx, user: str, *, message: str):
        await self.bot.say("{}, {}".format(user, message))