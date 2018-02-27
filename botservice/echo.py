import asyncio
import discord
from discord.ext import commands
import re


class GhostTalkEntry:
    def __init__(self, message, channel):
        self.requester = message.author
        self.channel = channel

    def __str__(self):
        return self.message.content


class State:
    def __init__(self, bot):
        self.bot = bot
        self.echoes = asyncio.Queue()


class Echo:
    """
    Echo the string input in specified seconds
    """

    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def get_state(self, server):
        state = self.states.get(server.id)
        if state is None:
            state = State(self.bot)
            self.states[server.id] = state

    def __unload(self):
        pass

    @commands.command(pass_context=True, no_pm=False)
    async def echo(self, ctx, *, msg: str):
        await self.bot.say(msg)

    @echo.error
    async def echo_error(self, error, ctx):
        await self.bot.say("{0.message.author.mention} You didn't tell me what to say… :<".format(ctx))


    # TODO: This is so unsafe, add restrictions to who can ghost_talk to where
    @commands.command(pass_context=True, no_pm=False)
    async def ghost_talk(self, ctx, *, input: str):
        f = re.match(r'\"(?P<server>[^\"]*)\" \"(?P<channel>[^\"]*)\"', input)

        try:
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

            await self.bot.say('Sending message to {}…'.format(channel.mention))
            await self.bot.send_message(channel, input[f.end() + 1:])
        except Exception as e:
            await self.bot.send_message(ctx.message.channel, '```py\n{}```'.format(e))
