"""``/derpi`` and ``/e621`` — booru search via the neutral booru skills.

There is no explicit *option*: the safety floor follows the channel. In a SFW
channel results are restricted to the safe rating; in a NSFW channel every rating
is allowed (the skill derives this from ``ctx.capabilities.allows_explicit``,
surfaced from ``channel.is_nsfw()``). Each command's ``sort`` choices are
generated from that site's own ``Sort`` enum.
"""

from __future__ import annotations

from enum import StrEnum

import discord
from discord import app_commands
from discord.ext import commands

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.frontends.discord import render
from petbot.frontends.discord.context import build_context


def _sort_choices(sort_enum: type[StrEnum]) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=member.name, value=member.value) for member in sort_enum]


_DERPI_SORTS = _sort_choices(derpibooru.Sort)
_E621_SORTS = _sort_choices(e621.Sort)


class BooruCog(commands.Cog):
    def __init__(self, bot: commands.Bot, derpi: DerpiSkill, e621: E621Skill) -> None:
        self.bot = bot
        self._derpi = derpi
        self._e621 = e621

    @app_commands.command(name="derpi", description="Search Derpibooru for an image.")
    @app_commands.describe(tags="Comma-separated tags.", sort="How to order matches.")
    @app_commands.choices(sort=_DERPI_SORTS)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def derpi(
        self, interaction: discord.Interaction, tags: str, sort: str = "random"
    ) -> None:
        await interaction.response.defer(thinking=True)
        ctx = build_context(interaction)
        result = await self._derpi.run({"tags": tags, "sort": sort}, ctx)
        await render.respond(interaction, result)

    @app_commands.command(name="e621", description="Search e621 for an image.")
    @app_commands.describe(tags="Comma-separated tags.", sort="How to order matches.")
    @app_commands.choices(sort=_E621_SORTS)
    @app_commands.allowed_installs(guilds=True, users=False)
    async def e621(self, interaction: discord.Interaction, tags: str, sort: str = "random") -> None:
        await interaction.response.defer(thinking=True)
        ctx = build_context(interaction)
        result = await self._e621.run({"tags": tags, "sort": sort}, ctx)
        await render.respond(interaction, result)
