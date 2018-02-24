import discord
from discord.ext import commands

import json
import argparse

from botservice import playmusic, echo, imagesearch

parser = argparse.ArgumentParser()
parser.add_argument('-p', '--prod',
                    help="Run bot using production secretkey instead of default dev keys.",
                    action='store_true')
args = parser.parse_args()

secret_keys = json.load(open('secretkeys.json')) if args.prod else json.load(open('secretkeys_dev.json'))

bot = commands.Bot(command_prefix=commands.when_mentioned_or(secret_keys['command']), description='PetBot')
bot.add_cog(playmusic.Music(bot))
bot.add_cog(echo.Echo(bot))
bot.add_cog(imagesearch.ImageSearch(bot))

@bot.event
async def on_ready():
    print('Logged in as {0.user}. \nDiscord version {1.version_info}.'.format(bot, discord))

if __name__ == '__main__':
    bot.run(secret_keys['token'])
