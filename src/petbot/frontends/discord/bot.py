"""The Discord frontend: hold the gateway, turn an @mention or slash command into a
dispatched call, render the result.

The thin, always-on driver. It runs no skills and no process logic: every @mention
becomes a :class:`~petbot.domain.input.TextInput` and every slash command a
:class:`~petbot.domain.input.CommandInput`, dispatched to a compute service through a
:class:`~petbot.platform.ProcessClient` (over an HTTP or Lambda transport); the neutral
:class:`~petbot.domain.result.SkillResult` is rendered back. Slash commands are derived
from the typed :data:`~petbot.types.CATALOG`, so the frontend still never imports a skill.
"""

from __future__ import annotations

import logging
from typing import assert_never

import discord
import httpx
from discord.ext import commands

from petbot.domain import History, Process, Recalled, SkillResult, TextInput, Unrecalled
from petbot.frontends.discord.context import build_context
from petbot.frontends.discord.history import reconstruct, replying_to_self, strip_self_mention
from petbot.frontends.discord.render import SERVICE_UNREACHABLE, respond
from petbot.frontends.discord.settings import DiscordSettings, HttpService, LambdaService
from petbot.frontends.discord.slash import build_commands
from petbot.logging_setup import configure_logging
from petbot.platform import HttpTransport, LambdaTransport, ProcessClient

logger = logging.getLogger(__name__)


class PetBot(commands.Bot):
    """The Discord gateway client; @mention is the conversational entrypoint."""

    def __init__(self, settings: DiscordSettings) -> None:
        intents = discord.Intents.default()
        # The conversational entrypoint needs the privileged message-content intent;
        # slash commands would not, but chat does.
        intents.message_content = True
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=intents,
            description="PetBot",
            activity=discord.CustomActivity(name="@ me to chat 🐾"),
        )
        self.settings = settings
        self._http: httpx.AsyncClient | None = None
        self.process: Process | None = None

    async def setup_hook(self) -> None:
        service = self.settings.service
        match service:
            case LambdaService(function_name=fn):
                self.process = ProcessClient(LambdaTransport.from_function_name(fn))
            case HttpService(url=url):
                self._http = httpx.AsyncClient(timeout=30.0)
                self.process = ProcessClient(HttpTransport(url, self._http))
            case _:
                assert_never(service)
        # Build the slash commands once the process client is wired; the closure
        # captures it. Each command rides the shared CommandInput dispatch path.
        for command in build_commands(self.process):
            self.tree.add_command(command)
        await self._sync_commands()

    async def _sync_commands(self) -> None:
        """Register the app commands with Discord. ``dev_guild_id`` syncs to that
        guild (instant, for iteration); otherwise a global sync (which Discord can
        take up to an hour to propagate the first time)."""
        if self.settings.dev_guild_id is not None:
            guild = discord.Object(id=self.settings.dev_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        if self.user is not None:
            logger.info("Logged in as %s (discord.py %s).", self.user, discord.__version__)

    async def on_message(self, message: discord.Message) -> None:
        # Conversational entry: an @mention, OR a reply to one of PetBot's own messages
        # (so a follow-up needs no re-mention). Other bots and our own messages are ignored.
        if message.author.bot or self.user is None:
            return
        bot_user_id = self.user.id
        if self.user not in message.mentions and not replying_to_self(message, bot_user_id):
            return
        text = strip_self_mention(message.content, bot_user_id).strip()
        if not text:
            return
        history = await self._reply_context(message, bot_user_id)
        await respond(
            message.channel, await self._respond(text, message, history), reference=message
        )

    async def _reply_context(self, message: discord.Message, bot_user_id: int) -> History:
        """Reconstruct the reply-chain history into a :class:`Recalled` — the single boundary
        for a reconstruction error. An unreadable chain (e.g. a missing ``Read Message
        History`` permission) is *raised* by the walk, caught here, logged loudly, and turned
        into :class:`Unrecalled` so the agent is told it lost the thread instead of answering
        blind (ADR 0009: errors are raised, handled once at a boundary)."""
        try:
            return Recalled(
                turns=await reconstruct(
                    message, bot_user_id=bot_user_id, max_turns=self.settings.history_max_turns
                )
            )
        except discord.HTTPException:
            logger.exception(
                "reply chain unreadable (e.g. missing 'Read Message History'); "
                "telling the agent it lost the thread"
            )
            return Unrecalled()

    async def _respond(self, text: str, message: discord.Message, history: History) -> SkillResult:
        """Dispatch the conversational turn, mapping any transport failure to a friendly
        result.

        A transport failure is the one error the frontend renders itself: the styler is
        on the far side of the unreachable connection, so this fallback is static."""
        assert self.process is not None
        try:
            async with message.channel.typing():
                return await self.process.respond(
                    TextInput(text=text, history=history), build_context(message)
                )
        except Exception:
            logger.exception("dispatch failed")
            return SkillResult.message(SERVICE_UNREACHABLE)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        await super().close()


def run(settings: DiscordSettings) -> None:
    """Start the Discord frontend (blocking)."""
    configure_logging(settings.log_level)
    logger.info("Starting PetBot Discord frontend (service=%s).", settings.service.kind)
    PetBot(settings).run(settings.discord_token, log_handler=None)
