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

