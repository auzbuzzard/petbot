"""``/derpi`` and ``/e621`` — booru search via the neutral booru skills.

There is no explicit *option*: the safety floor follows the channel (a SFW channel
restricts to the safe rating; a NSFW channel allows every rating), derived inside
the skill from ``ctx.capabilities.allows_explicit``. ``sort`` exposes each site's
full native ordering via autocomplete (too many to fit Discord's 25-choice cap);
``file_type`` and ``min_score`` are optional refinements.
"""

from __future__ import annotations

import logging
from enum import StrEnum

import discord
from discord import app_commands
from discord.ext import commands

from petbot.core.capabilities.boorus import derpibooru, e621
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.frontends.discord import render
from petbot.frontends.discord.context import build_context

logger = logging.getLogger(__name__)


def _match_sort(sort_enum: type[StrEnum], current: str) -> list[app_commands.Choice[str]]:
    cur = current.lower()
    matches = [m for m in sort_enum if cur in m.name.lower() or cur in m.value.lower()]
    return [app_commands.Choice(name=f"{m.name} ({m.value})", value=m.value) for m in matches[:25]]


def _file_types(file_type_enum: type[StrEnum]) -> list[app_commands.Choice[str]]:
    return [app_commands.Choice(name=m.name, value=m.value) for m in file_type_enum]


class BooruCog(commands.Cog):
    def __init__(self, bot: commands.Bot, derpi: DerpiSkill, e621: E621Skill) -> None:
        self.bot = bot
        self._derpi = derpi
        self._e621 = e621

    @app_commands.command(name="derpi", description="Search Derpibooru for an image.")
    @app_commands.describe(
        tags="Comma-separated tags (spaces allowed within a tag).",
        sort="How to order matches.",
        descending="Sort descending (default) or ascending.",
        file_type="Restrict to a file type.",
        min_score="Only results with at least this score.",
    )
    @app_commands.choices(file_type=_file_types(derpibooru.FileType))
    @app_commands.allowed_installs(guilds=True, users=False)
    async def derpi(
        self,
        interaction: discord.Interaction,
        tags: str,
        sort: str | None = None,
        descending: bool = True,
        file_type: str | None = None,
        min_score: int | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        logger.debug("/derpi invoked by %s: tags=%r", interaction.user, tags)
        args = _args(tags, sort, file_type, min_score)
        args["descending"] = descending
        result = await self._derpi.run(args, build_context(interaction))
        await render.respond(interaction, result)

    @derpi.autocomplete("sort")
    async def _derpi_sort(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return _match_sort(derpibooru.Sort, current)

    @app_commands.command(name="e621", description="Search e621 for an image.")
    @app_commands.describe(
        tags="Space-separated tags (use underscores within a tag, e.g. twilight_sparkle).",
        sort="How to order matches.",
        file_type="Restrict to a file type.",
        min_score="Only results with at least this score.",
    )
    @app_commands.choices(file_type=_file_types(e621.FileType))
    @app_commands.allowed_installs(guilds=True, users=False)
    async def e621(
        self,
        interaction: discord.Interaction,
        tags: str,
        sort: str | None = None,
        file_type: str | None = None,
        min_score: int | None = None,
    ) -> None:
        await interaction.response.defer(thinking=True)
        logger.debug("/e621 invoked by %s: tags=%r", interaction.user, tags)
        result = await self._e621.run(
            _args(tags, sort, file_type, min_score), build_context(interaction)
        )
        await render.respond(interaction, result)

    @e621.autocomplete("sort")
    async def _e621_sort(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return _match_sort(e621.Sort, current)


def _args(
    tags: str, sort: str | None, file_type: str | None, min_score: int | None
) -> dict[str, object]:
    args: dict[str, object] = {"tags": tags}
    if sort:
        args["sort"] = sort
    if file_type:
        args["file_type"] = file_type
    if min_score is not None:
        args["min_score"] = min_score
    return args
