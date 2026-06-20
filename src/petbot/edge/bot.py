"""The Discord edge: hold the gateway, turn an @mention or slash command into a
dispatched call, render the result.

The thin, always-on process. It runs no skills: every @mention (chat) and every
slash command is dispatched to a worker through the typed :class:`petbot.types.Skills`
client (a :class:`~petbot.platform.SkillsClient` over an HTTP or Lambda transport),
and the worker's neutral :class:`~petbot.domain.result.SkillResult` is rendered back.
Slash commands are defined from the typed ``*Args`` surface, so the edge still never
imports a skill. It owns a live connection, so the gateway wiring is smoke-tested
manually against a dev guild; the dispatch/render helpers are unit-tested with fakes.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable
from inspect import Parameter, Signature
from typing import Any, assert_never

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from petbot.domain import SkillResult
from petbot.edge.context import build_context, build_interaction_context
from petbot.edge.render import respond, respond_interaction
from petbot.edge.settings import EdgeSettings, HttpWorker, LambdaWorker
from petbot.logging_setup import configure_logging
from petbot.platform import HttpTransport, LambdaTransport, SkillsClient
from petbot.types import COMMANDS, ChatArgs, CommandSpec, Skills

logger = logging.getLogger(__name__)

#: Shown when the edge can't reach the worker (any transport error).
_WORKER_UNREACHABLE = "uwu I couldn't reach my brain right now — please try again soon."


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
            case _:
                assert_never(worker)
        self._register_slash_commands()
        await self._sync_commands()

    @property
    def _client(self) -> Skills:
        assert self.skills is not None  # set above in setup_hook, before any interaction
        return self.skills

    def _register_slash_commands(self) -> None:
        """One slash command per manifest entry, its options generated from the
        skill's ``args_model`` — so the edge hand-lists neither skills nor args."""
        for spec in COMMANDS:
            self.tree.add_command(self._build_command(spec))

    def _build_command(self, spec: CommandSpec) -> app_commands.Command[Any, ..., None]:
        """Turn a manifest entry into a slash command: one option per ``args_model``
        field (its name, type, and required/optional read straight off the model),
        dispatched through the Skills client by the shared :meth:`_run_slash`."""

        async def callback(interaction: discord.Interaction, **values: Any) -> None:
            args = spec.args_model(**values)
            ctx = build_interaction_context(interaction)
            await self._run_slash(interaction, spec.invoke(self._client, args, ctx))

        params = [
            Parameter(
                "interaction", Parameter.POSITIONAL_OR_KEYWORD, annotation=discord.Interaction
            )
        ]
        for name, field_info in spec.args_model.model_fields.items():
            default = Parameter.empty if field_info.is_required() else field_info.default
            params.append(
                Parameter(
                    name,
                    Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=field_info.annotation,
                    default=default,
                )
            )
        # discord.py reads the callback's signature to build the options; the real
        # callback takes **values, so attach the schema-bearing signature explicitly.
        callback.__signature__ = Signature(params)  # type: ignore[attr-defined]
        callback.__discord_app_commands_param_description__ = {  # type: ignore[attr-defined]
            name: name.replace("_", " ") for name in spec.args_model.model_fields
        }
        return app_commands.Command(name=spec.name, description=spec.description, callback=callback)

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

    async def _run_slash(
        self, interaction: discord.Interaction, call: Awaitable[SkillResult]
    ) -> None:
        """Defer, run the dispatched ``call``, send the result as a followup.

        Defer first: a dispatch can exceed Discord's 3s interaction window on a
        Lambda cold start. A transport failure maps to a friendly result, not a crash.
        """
        await interaction.response.defer()
        try:
            result = await call
        except Exception:
            logger.exception("slash dispatch failed")
            result = SkillResult.failure(_WORKER_UNREACHABLE)
        await respond_interaction(interaction, result)

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
            return SkillResult.failure(_WORKER_UNREACHABLE)

    async def close(self) -> None:
        if self._http is not None:
            await self._http.aclose()
        await super().close()


def run(settings: EdgeSettings) -> None:
    """Start the edge (blocking)."""
    configure_logging(settings.log_level)
    logger.info("Starting PetBot edge (worker=%s).", settings.worker.kind)
    PetBot(settings).run(settings.discord_token, log_handler=None)
