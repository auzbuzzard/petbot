"""Talk to the core service from a terminal: ``python -m petbot.services.core.chat``.

No Discord and no server, but otherwise production's path: each message is encoded as the
transports encode a dispatch and handed to :func:`~petbot.platform.serve`, which runs the
process the Lambda builds (:func:`~petbot.services.core.build_process`: this checkout's
code, prompts and tools, with the model and keys from the environment, as in
``.env.example``) under the Lambda's time budget. An unexpected error becomes the reply
production would send (its traceback is logged) and the conversation goes on. Each reply is
shown as the Discord frontend posts it, after the agent's tool calls; ``-v`` adds exactly
what each call returned to the model.

``--lambda FUNCTION`` sends the same conversation to a deployed core instead (a dev core
running an unmerged branch), invoked over the frontend's own
:class:`~petbot.platform.LambdaTransport` with the caller's AWS credentials. The turn then
runs in the Lambda, on its configuration, network and time budget; its tool calls are in its
logs, not shown here, and a failed dispatch gets the reply the frontend posts.

A conversation is a JSON file (examples in ``conversations/``)::

    {"server": "Test server", "channel": "general", "nsfw": false,
     "messages": [
       {"author": "Robin", "text": "give us a random easy leetcode problem"},
       {"author": "Sam", "text": "we already did that one", "to_bot": false}
     ]}

Each message is sent to PetBot unless ``to_bot`` is false (people talking among
themselves). The messages form one reply chain, each replying to the one before, from the
last ``"fresh": true`` message (a new @mention) on, and PetBot's history is that chain as the
frontend reads it back: at most ``HISTORY_MAX_TURNS`` messages, his own as he posted them.
As in Discord, only the first message of a reply that is split across several carries the
reply, so the next message, replying to the last of them, starts the chain there.
``"server": null`` is a direct message. ``--say`` sends one message instead of a file.

Tool calls are read from the turn's agent run (:func:`pydantic_ai.capture_run_messages`). A
turn whose history the model rejected for length, retried after compaction, shows the first
attempt's calls only. The harness reuses the Discord frontend's rendering and history code,
so it needs the full dev install (``uv sync --all-extras``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import Annotated, TextIO

from pydantic import StringConstraints, ValidationError
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from petbot.domain import (
    Frozen,
    Platform,
    Process,
    Recalled,
    SkillContext,
    SkillResult,
    TextInput,
    User,
)
from petbot.frontends.discord.history import DiscordTurn, describe_card, to_turns
from petbot.frontends.discord.render import SERVICE_UNREACHABLE, plan
from petbot.frontends.discord.settings import DiscordSettings
from petbot.logging_setup import configure_logging
from petbot.observability import (
    ObservabilitySettings,
    configure_observability,
    flush_observability,
)
from petbot.platform import LambdaTransport, ProcessClient, budget, serve
from petbot.services.core import RESERVE_SECONDS, build_process

logger = logging.getLogger(__name__)

#: PetBot's name on his own messages.
BOT_NAME = "PetBot"
#: PetBot's user id in the reconstructed chain; no message here mentions him by id.
_BOT_USER_ID = 0

#: The core Lambda's timeout by default: the ``timeout`` default in
#: ``deploy/terraform/variables.tf``. Pass ``--timeout`` when the deployment sets another.
DEFAULT_TIMEOUT = 120.0

#: A message's text as the frontend sends it: stripped, and never empty.
_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Message(Frozen):
    """One message in a conversation."""

    author: str
    text: _Text
    #: Sent to PetBot (a mention or a reply to him); false is people talking to each other.
    to_bot: bool = True
    #: A new @mention rather than a reply: the chain, and so PetBot's history, starts here.
    fresh: bool = False


class Conversation(Frozen):
    """Where a conversation happens, and what is said in it, in order."""

    server: str | None = "Test server"
    channel: str | None = "general"
    nsfw: bool = False
    messages: tuple[Message, ...]


class ChainSettings(BaseSettings):
    """How far back the frontend reads a reply chain, from its own ``HISTORY_MAX_TURNS``."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    history_max_turns: int = DiscordSettings.model_fields["history_max_turns"].default


def context_for(conversation: Conversation, author: str) -> SkillContext:
    """The request context a message from ``author`` arrives with."""
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id=f"local:{author}", display_name=author),
        conversation_id="local:chat",
        allows_explicit=conversation.nsfw,
        community_name=conversation.server,
        channel_name=conversation.channel if conversation.server is not None else None,
    )


def _wire(inp: TextInput, ctx: SkillContext) -> str:
    """The dispatch body, as the transports encode it."""
    return json.dumps(
        {"input": inp.model_dump(mode="json"), "context": ctx.model_dump(mode="json")}
    )


def print_tool_calls(messages: Sequence[ModelMessage], out: TextIO, *, verbose: bool) -> None:
    """Each tool call in a turn's agent run, with what the model got back for it.

    The run's history holds only text turns, so every call in ``messages`` is this turn's.
    """
    answers: dict[str, ToolReturnPart | RetryPromptPart] = {
        part.tool_call_id: part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    }
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for call in (p for p in message.parts if isinstance(p, ToolCallPart)):
            answer = answers.get(call.tool_call_id)
            if isinstance(answer, ToolReturnPart):
                status, detail = "", answer.model_response_str()
            elif isinstance(answer, RetryPromptPart):
                status, detail = (
                    " (rejected; the model was asked to retry)",
                    answer.model_response(),
                )
            else:
                status, detail = " (no result: the turn ended first)", ""
            print(f"  [{call.tool_name}] {call.args_as_json_str()}{status}", file=out)
            if verbose and detail:
                print("    " + detail.replace("\n", "\n    "), file=out)


class Core(ABC):
    """Where the harness sends each message."""

    @abstractmethod
    async def reply(
        self, inp: TextInput, ctx: SkillContext
    ) -> tuple[SkillResult, Sequence[ModelMessage] | None]:
        """PetBot's reply, and the turn's agent run when it ran here (``None`` otherwise)."""


class InProcess(Core):
    """This checkout's core process, served in-process under a Lambda's time budget."""

    def __init__(self, process: Process, *, seconds: float) -> None:
        self._process = process
        self._seconds = seconds

    async def reply(
        self, inp: TextInput, ctx: SkillContext
    ) -> tuple[SkillResult, Sequence[ModelMessage] | None]:
        with budget(self._seconds), capture_run_messages() as run:
            result = SkillResult.model_validate_json(await serve(self._process, _wire(inp, ctx)))
        return result, run


class Deployed(Core):
    """A deployed core, dispatched to as the Discord frontend dispatches: a failure is
    logged and answered with the frontend's own fallback."""

    def __init__(self, process: Process) -> None:
        self._process = process

    async def reply(
        self, inp: TextInput, ctx: SkillContext
    ) -> tuple[SkillResult, Sequence[ModelMessage] | None]:
        try:
            return await self._process.respond(inp, ctx), None
        except Exception:
            logger.exception("dispatch failed")
            return SkillResult.message(SERVICE_UNREACHABLE), None


async def replay(
    core: Core,
    conversation: Conversation,
    out: TextIO,
    *,
    max_turns: int,
    verbose: bool = False,
) -> list[str]:
    """Send each message to ``core`` in turn, printing the exchange to ``out``. Returns
    what PetBot posted for each message sent to him."""
    chain: list[DiscordTurn] = []  # oldest first
    replies: list[str] = []
    for message in conversation.messages:
        if message.fresh:
            chain.clear()
        print(f"{message.author}: {message.text}", file=out)
        posts: list[str] = []
        if message.to_bot:
            # The frontend walks back from the new message: its newest ancestors first.
            history = to_turns(chain[::-1][:max_turns], bot_user_id=_BOT_USER_ID)
            inp = TextInput(text=message.text, history=Recalled(turns=history))
            result, run = await core.reply(inp, context_for(conversation, message.author))
            if run is not None:
                print_tool_calls(run, out, verbose=verbose)
            for content, embed in plan(result):
                card = describe_card(embed) if embed is not None else ""
                # A message's text as the frontend reads it back: its content, else its card.
                posts.append(content or card)
                print(f"{BOT_NAME}: {content or ''}", file=out)
                if card:
                    print(f"  {card}", file=out)
            print(file=out)
            replies.append("\n".join(posts))
        chain.append(DiscordTurn(display_name=message.author, is_self=False, text=message.text))
        if len(posts) > 1:
            chain.clear()
        if posts:
            chain.append(DiscordTurn(display_name=BOT_NAME, is_self=True, text=posts[-1]))
    return replies


def _parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m petbot.services.core.chat",
        description="Run a conversation through PetBot's core, with no Discord.",
    )
    parser.add_argument("conversation", nargs="?", type=Path, help="a conversation JSON file")
    parser.add_argument("--say", help="send one message instead of a file")
    parser.add_argument("--as", dest="author", help="who --say is from (default: tester)")
    parser.add_argument("--nsfw", action="store_true", help="--say in an age-gated channel")
    parser.add_argument(
        "--timeout",
        type=float,
        help="the core Lambda's timeout in seconds; each turn's budget is this less the "
        f"handler's reserve, as in production (default {DEFAULT_TIMEOUT:g})",
    )
    parser.add_argument(
        "--lambda",
        dest="function",
        metavar="FUNCTION",
        help="send the conversation to this deployed core Lambda (e.g. petbot-dev-core) "
        "instead of running this checkout in-process",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print tool output")
    args = parser.parse_args(argv)
    if args.function is not None and (args.timeout is not None or args.verbose):
        parser.error("--timeout and -v run in-process; a deployed core keeps its own")
    if args.timeout is None:
        args.timeout = DEFAULT_TIMEOUT
    if args.conversation is None and args.say is None:
        parser.error("give a conversation file or --say")
    if args.conversation is not None and args.say is not None:
        parser.error("give a conversation file or --say, not both")
    if args.conversation is not None and (args.author is not None or args.nsfw):
        parser.error("--as and --nsfw go with --say; a conversation file sets its own")
    if args.author is None:
        args.author = "tester"
    return args


def _conversation(args: argparse.Namespace) -> Conversation:
    try:
        if args.say is not None:
            message = Message(author=args.author, text=args.say)
            return Conversation(nsfw=args.nsfw, messages=(message,))
        return Conversation.model_validate_json(args.conversation.read_text("utf-8"))
    except OSError as exc:
        raise SystemExit(f"Can't read {args.conversation}: {exc.strerror}") from exc
    except ValidationError as exc:
        raise SystemExit(f"Not a valid conversation:\n{exc}") from exc


def _core(args: argparse.Namespace) -> Core:
    if args.function is not None:
        return Deployed(ProcessClient(LambdaTransport.from_function_name(args.function)))
    return InProcess(build_process(), seconds=max(0.0, args.timeout - RESERVE_SECONDS))


async def _run(args: argparse.Namespace, conversation: Conversation) -> None:
    try:
        core = _core(args)
        max_turns = ChainSettings().history_max_turns
    except ValidationError as exc:
        raise SystemExit(
            f"The core's settings are missing or invalid (see .env.example):\n{exc}"
        ) from exc
    await replay(core, conversation, sys.stdout, max_turns=max_turns, verbose=args.verbose)


def main(argv: list[str] | None = None) -> None:
    args = _parse(argv)
    conversation = _conversation(args)
    configure_logging(os.environ.get("LOG_LEVEL", "WARNING"))
    try:
        configure_observability(ObservabilitySettings())
    except ValidationError as exc:
        raise SystemExit(f"The telemetry settings are invalid:\n{exc}") from exc
    try:
        asyncio.run(_run(args, conversation))
    finally:
        flush_observability()


if __name__ == "__main__":
    main()
