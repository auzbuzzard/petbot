"""The Discord edge: hold the gateway, turn an @mention into a chat call, render.

The thin, always-on process. It runs no skills: every mention is dispatched to a
worker through the typed :class:`petbot.types.Skills` client (a
:class:`~petbot.platform.SkillsClient` over an HTTP or Lambda transport), and the
worker's neutral :class:`~petbot.domain.result.SkillResult` is rendered back to
the channel. It owns a live connection, so it is smoke-tested manually against a
dev guild rather than in CI.
"""

from __future__ import annotations

import logging
import re

import discord
import httpx
from discord.ext import commands

from petbot.domain import SkillResult
from petbot.edge.context import build_context
from petbot.edge.render import respond
from petbot.edge.settings import EdgeSettings, HttpWorker, LambdaWorker
from petbot.logging_setup import configure_logging
from petbot.platform import HttpTransport, LambdaTransport, SkillsClient
from petbot.types import ChatArgs, Skills

logger = logging.getLogger(__name__)


def _without_mention(content: str, user_id: int) -> str:
    """Remove only this bot's mention (``<@id>`` / ``<@!id>``), leaving others intact."""
    return re.sub(rf"<@!?{user_id}>", "", content)


class PetBot(commands.Bot):
    """The edge gateway client; @mention is the conversational entrypoint."""

    def __init__(self, settings: EdgeSettings) -> None:
        intents = discord.Intents.default()
        # The conversational entrypoint needs the privileged message-content
        # intent; slash commands would not, but chat does.
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            description="PetBot",
            activity=discord.CustomActivity(name="@ me to chat 🐾"),
        )
        self.settings = settings
        self._http: httpx.AsyncClient | None = None
        self.skills: Skills | None = None

    async def setup_hook(self) -> None:
        worker = self.settings.worker
        match worker:
            case LambdaWorker(function_name=fn):
                self.skills = SkillsClient(LambdaTransport.from_function_name(fn))
            case HttpWorker(url=url):
                self._http = httpx.AsyncClient(timeout=30.0)
                self.skills = SkillsClient(HttpTransport(url, self._http))

    async def on_ready(self) -> None:
        if self.user is not None:
            logger.info("Logged in as %s (discord.py %s).", self.user, discord.__version__)

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or self.user is None or self.user not in message.mentions:
            return
        text = _without_mention(message.content, self.user.id).strip()
        if not text:
            return
        await respond(message.channel, await self._chat(text, message))

    async def _chat(self, text: str, message: discord.Message) -> SkillResult:
        """Dispatch to the worker, mapping any transport failure to a friendly result."""
        assert self.skills is not None
        try:
            async with message.channel.typing():
                return await self.skills.chat(ChatArgs(message=text), build_context(message))
        except Exception:
            logger.exception("dispatch failed")
            return SkillResult.failure(
                "uwu I couldn't reach my brain right now — please try again soon."
            )

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        await super().close()


def run(settings: EdgeSettings) -> None:
    """Start the edge (blocking)."""
    configure_logging(settings.log_level)
    logger.info("Starting PetBot edge (worker=%s).", settings.worker.kind)
    PetBot(settings).run(settings.discord_token, log_handler=None)
