import discord
from discord.ext import commands

import json

import petdj

secret_keys = json.load(open('secretkeys.json'))

bot = commands.Bot(command_prefix=commands.when_mentioned_or('$'), description='PetBot')
bot.add_cog(petdj.Music(bot))


@bot.command()
async def echo(*, msg: str):
    await bot.say(msg)


@bot.event
async def on_ready():
    print('Logged in as {0.user}. \nDiscord version {1.version_info}.'.format(bot, discord))

if __name__ == '__main__':
    bot.run(secret_keys['token'])
