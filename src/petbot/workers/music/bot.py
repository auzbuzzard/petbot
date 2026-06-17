"""The music worker: a Discord gateway that also hosts the music skill.

Music is its own worker because voice can't go serverless — it needs a persistent
gateway and a UDP voice socket. So this process holds a gateway (for voice state +
playback) *and* an HTTP dispatch endpoint the edge calls: an inbound dispatched
call is run by a :class:`~petbot.platform.Worker` hosting a single
:class:`~petbot.skills.music.MusicSkill`, whose
:class:`~petbot.domain.ports.VoiceProvider` resolves a live voice port from this
gateway's cache. Smoke-tested manually against a dev guild, not in CI.
"""

from __future__ import annotations

import logging

import discord
from aiohttp import web

from petbot.logging_setup import configure_logging
from petbot.platform import Worker
from petbot.skills.music import MusicSkill
from petbot.workers.music.provider import DiscordVoiceProvider
from petbot.workers.music.settings import MusicSettings

logger = logging.getLogger(__name__)


class MusicWorker(discord.Client):
    """Gateway client that serves dispatched music calls over HTTP."""

    def __init__(self, settings: MusicSettings) -> None:
        intents = discord.Intents.default()
        intents.voice_states = True
        intents.members = True  # needed to resolve the invoking member for voice
        super().__init__(intents=intents)
        self.settings = settings
        self.worker = Worker([MusicSkill(DiscordVoiceProvider(self))])
        self._runner: web.AppRunner | None = None

    async def setup_hook(self) -> None:
        app = web.Application()
        app.router.add_post("/dispatch", self._dispatch)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.settings.dispatch_host, self.settings.dispatch_port)
        await site.start()
        logger.info(
            "music worker dispatch on http://%s:%d/dispatch",
            self.settings.dispatch_host,
            self.settings.dispatch_port,
        )

    async def _dispatch(self, request: web.Request) -> web.Response:
        body = await request.read()
        out = await self.worker.serve(body)
        return web.Response(body=out.encode(), content_type="application/json")

    async def close(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
        await super().close()


def run(settings: MusicSettings) -> None:
    """Start the music worker (blocking)."""
    configure_logging(settings.log_level)
    logger.info("Starting PetBot music worker.")
    MusicWorker(settings).run(settings.discord_token, log_handler=None)
