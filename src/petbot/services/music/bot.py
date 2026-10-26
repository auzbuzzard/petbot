"""The music compute service: a Discord gateway that also runs the music command process.

So this process holds a gateway (for voice state +
playback) *and* an HTTP dispatch endpoint the frontend calls. An inbound dispatch is run
by a :class:`~petbot.process.RouterProcess` hosting a single
:class:`~petbot.process.CommandProcess` over a one-skill
:class:`~petbot.platform.ToolRegistry` (the :class:`~petbot.skills.music.MusicSkill`,
whose :class:`~petbot.domain.ports.VoiceProvider` resolves a live voice port from this
gateway's cache). There is no conversational process here (``chat=None``).
"""

from __future__ import annotations

import logging

import discord
from aiohttp import web

from petbot.logging_setup import configure_logging
from petbot.observability import ObservabilitySettings, configure_observability
from petbot.platform import ToolRegistry, serve
from petbot.process import CommandProcess, PassthroughStyle, RouterProcess
from petbot.services.music.provider import DiscordVoiceProvider
from petbot.services.music.settings import MusicSettings
from petbot.skills.music import MusicSkill

logger = logging.getLogger(__name__)


class MusicService(discord.Client):
    def __init__(self, settings: MusicSettings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.members = True
        super().__init__(intents=intents)
        self.settings = settings
        registry = ToolRegistry([MusicSkill(DiscordVoiceProvider(self))])
        command = CommandProcess(registry, PassthroughStyle())
        self.process = RouterProcess(chat=None, command=command)
        self._runner: web.AppRunner | None = None

    async def setup_hook(self) -> None:
        app = web.Application()
        app.router.add_post("/dispatch", self._dispatch)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.settings.dispatch_host, self.settings.dispatch_port)
        await site.start()
        logger.info(
            "music service dispatch on http://%s:%d/dispatch",
            self.settings.dispatch_host,
            self.settings.dispatch_port,
        )

    async def _dispatch(self, request: web.Request) -> web.Response:
        body = await request.read()
        out = await serve(self.process, body)
        return web.Response(body=out.encode(), content_type="application/json")

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        await super().close()


def run(settings: MusicSettings) -> None:
    configure_logging(settings.log_level)
    configure_observability(ObservabilitySettings())
    logger.info("Starting PetBot music service.")
    MusicService(settings).run(settings.discord_token, log_handler=None)
