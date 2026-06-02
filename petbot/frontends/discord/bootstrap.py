"""Discord gateway bootstrap: intents, dependency wiring, and slash-command sync.

This module owns the live connection and is therefore smoke-tested manually
against a dev guild rather than in CI. It builds the shared httpx client and
the skill registry, attaches the cogs, and syncs the command tree (instantly to
the dev guild in ``dev``, globally in ``prod``).
"""

from __future__ import annotations

import logging

import discord
import httpx
from discord.ext import commands

from petbot.config import Settings
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.core.skills.context import Capabilities
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.music_skill import MusicSkill
from petbot.core.skills.registry import SkillRegistry
from petbot.frontends.discord.cogs.admin_cog import AdminCog
from petbot.frontends.discord.cogs.booru_cog import BooruCog
from petbot.frontends.discord.cogs.math_cog import MathCog
from petbot.frontends.discord.cogs.music_cog import MusicCog
from petbot.frontends.discord.cogs.ping_cog import PingCog
from petbot.logging_setup import configure_logging

log = logging.getLogger(__name__)

# Capabilities the Discord frontend can offer (used to filter the registry, e.g.
# for the Phase B LLM tool list). Discord can supply a VoicePort, so voice is on.
DISCORD_CAPABILITIES = Capabilities(supports_voice=True, supports_rich_embeds=True)


class PetBot(commands.Bot):
    """The Discord client. Slash-command first; the prefix is vestigial."""

    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        # message_content stays OFF: slash commands don't need it, and it's a
        # privileged intent. It is only required once the Phase B chat/LLM layer
        # lands.
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            description="PetBot",
        )
        self.settings = settings
        self.http_client: httpx.AsyncClient | None = None
        self.registry: SkillRegistry | None = None

    async def setup_hook(self) -> None:
        self.http_client = httpx.AsyncClient(timeout=20.0)

        math_skill = MathSkill()
        derpi_skill = DerpiSkill(client=self.http_client, api_key=self.settings.derpibooru_api_key)
        e621_skill = E621Skill(
            client=self.http_client,
            user_agent=self.settings.user_agent,
            username=self.settings.e621_username,
            api_key=self.settings.e621_api_key,
        )
        music_skill = MusicSkill()

        self.registry = SkillRegistry([math_skill, derpi_skill, e621_skill, music_skill])

        await self.add_cog(PingCog(self))
        await self.add_cog(MathCog(self, math_skill))
        await self.add_cog(BooruCog(self, derpi_skill, e621_skill))
        await self.add_cog(MusicCog(self, music_skill))
        await self.add_cog(AdminCog(self))

        await self._sync_commands()

    async def _sync_commands(self) -> None:
        if self.settings.is_prod or self.settings.dev_guild_id is None:
            synced = await self.tree.sync()
            log.info("Synced %d global slash command(s).", len(synced))
            return
        guild = discord.Object(id=self.settings.dev_guild_id)
        # Instant, guild-scoped sync for fast iteration in dev.
        self.tree.copy_global_to(guild=guild)
        synced = await self.tree.sync(guild=guild)
        log.info("Synced %d slash command(s) to dev guild %s.", len(synced), guild.id)

    async def on_ready(self) -> None:
        if self.user is not None:
            log.info("Logged in as %s (discord.py %s).", self.user, discord.__version__)

    async def close(self) -> None:
        if self.http_client is not None:
            await self.http_client.aclose()
        await super().close()


def run(settings: Settings) -> None:
    """Start the bot (blocking) with the given settings.

    This is the single place logging is configured. ``log_handler=None`` stops
    discord.py from installing its own handler, so its ``discord.*`` loggers
    propagate into the handlers we set up here.
    """
    configure_logging(level=settings.log_level, fmt=settings.resolved_log_format)
    log.info("Starting PetBot (env=%s, log_format=%s).", settings.env, settings.resolved_log_format)
    bot = PetBot(settings)
    bot.run(settings.discord_token, log_handler=None)
