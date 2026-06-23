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
import re
from typing import assert_never

import discord
import httpx
from discord.ext import commands

from petbot.domain import History, Process, Recalled, SkillResult, TextInput, Unrecalled
from petbot.frontends.discord.context import build_context
from petbot.frontends.discord.history import reconstruct, resolve_parent
from petbot.frontends.discord.render import SERVICE_UNREACHABLE, respond
from petbot.frontends.discord.settings import DiscordSettings, HttpService, LambdaService
from petbot.frontends.discord.slash import build_commands
from petbot.logging_setup import configure_logging
from petbot.platform import HttpTransport, LambdaTransport, ProcessClient

logger = logging.getLogger(__name__)

#: A fresh reply context (no prior turns). Module-level so it isn't a function-call default.
_NO_HISTORY: History = Recalled()


def _without_mention(content: str, user_id: int) -> str:
    """Remove only this bot's mention (``<@id>`` / ``<@!id>``), leaving others intact."""
    return re.sub(rf"<@!?{user_id}>", "", content)


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
        parent = await self._reply_parent(message)
        replying_to_self = parent is not None and parent.author.id == bot_user_id
        if self.user not in message.mentions and not replying_to_self:
            return
        text = _without_mention(message.content, bot_user_id).strip()
        if not text:
            return
        history = await self._history_for(parent, bot_user_id)
        await respond(
            message.channel, await self._respond(text, message, history), reference=message
        )

    async def _reply_parent(self, message: discord.Message) -> discord.Message | None:
        """The message ``message`` replies to, or ``None`` if there isn't one or it can't
        be read.

        ``resolve_parent`` *raises* a Discord error (e.g. a missing ``Read Message
        History`` permission) rather than swallowing it; it is caught here and degraded to
        no parent. Kept separate from history reconstruction so a *walk* failure can't drop
        the parent the trigger check needs — PetBot still answers (just without memory).
        """
        try:
            return await resolve_parent(message)
        except Exception:
            logger.exception("resolving the reply parent failed; continuing without memory")
            return None

    async def _history_for(self, parent: discord.Message | None, bot_user_id: int) -> History:
        """Reconstruct the reply-chain history from the resolved ``parent`` into a
        :class:`Recalled`. A Discord error during the walk (e.g. a missing ``Read Message
        History`` permission) is caught here and becomes :class:`Unrecalled` — so the chat
        agent is told it lost the thread instead of answering blind (ADR 0009: errors are
        raised, handled once at a boundary)."""
        if parent is None:
            return _NO_HISTORY
        try:
            return Recalled(
                turns=await reconstruct(
                    parent,
                    bot_user_id=bot_user_id,
                    max_turns=self.settings.history_max_turns,
                    strip_mention=_without_mention,
                )
            )
        except Exception:
            logger.exception(
                "history reconstruction failed (e.g. missing 'Read Message History'); "
                "telling the agent it lost the thread"
            )
            return Unrecalled()

    async def _respond(
        self, text: str, message: discord.Message, history: History = _NO_HISTORY
    ) -> SkillResult:
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
