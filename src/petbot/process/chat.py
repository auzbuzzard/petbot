"""The chat process: PetBot's conversational LLM brain — the first-class process.

``@mention`` input arrives as a :class:`~petbot.domain.input.TextInput`; this runs the
pydantic-ai agent over the message, letting it call tools (its sibling skills) through
the injected :class:`~petbot.platform.registry.ToolRegistry`, then folds the model's
prose plus any rich card a tool produced into one neutral
:class:`~petbot.domain.result.SkillResult`. The agent voices its own reply, so the
output ``StylePort`` is a no-op (:class:`~petbot.process.voice.PassthroughStyle`) —
styling stays uniform across processes without a second LLM pass.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import assert_never

from opentelemetry import metrics
from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.models.instrumented import InstrumentationSettings
from pydantic_ai.settings import ModelSettings

from petbot.domain import (
    Input,
    Process,
    Recalled,
    SkillContext,
    SkillResult,
    StylePort,
    TextInput,
    Unrecalled,
)
from petbot.observability import hash_user_id
from petbot.platform import ToolRegistry, remaining
from petbot.process.agent import ChatDeps, build_agent
from petbot.process.context import (
    MAX_COMPACTION_RETRIES,
    Compactor,
    build_compactor,
    is_context_overflow,
)
from petbot.process.history import drop_leading_assistant, to_model_messages
from petbot.process.model import build_model
from petbot.process.settings import ChatSettings
from petbot.process.voice import PassthroughStyle

logger = logging.getLogger(__name__)

#: Per-run instruction added to PetBot's persona when a reply's prior context couldn't be
#: read (``Unrecalled``), so the agent voices that it lost the thread instead of guessing.
_LOST_CONTEXT_NOTE = (
    "The user is replying to earlier messages you can no longer see. If their message "
    "relies on that lost context, tell them you've lost the thread and ask them to recap; "
    "otherwise just answer normally."
)


#: The reply when a turn runs out of its time budget (see :mod:`petbot.platform.deadline`):
#: an answer in persona instead of the host killing the turn mid-run.
_OUT_OF_TIME = (
    "Ehh, that one took me too long to work out, sorry! >w< Could you ask again, maybe a "
    "little narrower?"
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _quoted(name: str) -> str:
    """A user-controlled name as one quoted, single-line token, so a display/server/channel
    name can't pose as another line of the instructions."""
    flat = " ".join(name.replace('"', "'").split())[:100]
    return f'"{flat}"'


def _place(ctx: SkillContext) -> str:
    if ctx.community_name is None:
        return "a direct message"
    server = f"the server {_quoted(ctx.community_name)}"
    if ctx.channel_name is None:
        return server
    return f"channel {_quoted(ctx.channel_name)} in {server}"


def run_context(ctx: SkillContext, now: datetime) -> str:
    """The per-run grounding added to the static persona: the clock, who is speaking, and
    where. Kept out of the static instructions so that prefix stays cacheable.

    The clock is UTC plus its Unix time: the agent doesn't know the reader's timezone, so
    it writes times as Discord timestamps, which each reader's client shows in their own.
    """
    utc = now.astimezone(UTC)
    rating = "age-gated (NSFW)" if ctx.allows_explicit else "not age-gated, so keep everything SFW"
    return "\n".join(
        (
            "Current context:",
            f"- Now: {utc:%A, %d %B %Y, %H:%M} UTC (Unix time {int(utc.timestamp())}).",
            f"- You are answering {_quoted(ctx.user.display_name)}, in {_place(ctx)}.",
            f"- This channel is {rating}.",
        )
    )


_meter = metrics.get_meter("petbot.process.chat")
_TOOL_CALLS = _meter.create_counter(
    "petbot.agent.tool_calls", description="Agent tool calls, by tool name."
)
_ZERO_TOOL_RUNS = _meter.create_counter(
    "petbot.agent.zero_tool_runs", description="Agent runs that called no tool."
)
_OUT_OF_TIME_RUNS = _meter.create_counter(
    "petbot.agent.out_of_time_runs",
    description="Agent runs stopped at the turn's time budget and answered with a fallback.",
)
_LOST_CONTEXT_RUNS = _meter.create_counter(
    "petbot.agent.lost_context_runs",
    description="Agent runs answered with an unreadable reply context (Unrecalled).",
)


class ChatProcess(Process):
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
        style: StylePort | None = None,
        instrumentation: InstrumentationSettings | None = None,
        id_salt: str = "",
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._registry = registry
        self._settings = settings or ChatSettings()
        self._model = model
        self._style: StylePort = style or PassthroughStyle()
        self._id_salt = id_salt
        self._clock = clock
        self._agent = build_agent(self._settings.system_prompt, instrumentation=instrumentation)
        self._compactor: Compactor = build_compactor(self._settings, model=model)
        thinking = self._settings.thinking
        self._model_settings = ModelSettings(thinking=thinking) if thinking is not None else None

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model(self._settings)
        return self._model

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        if not isinstance(inp, TextInput):
            raise TypeError(f"ChatProcess received {type(inp).__name__}")
        deps = ChatDeps(registry=self._registry, ctx=ctx)
        match inp.history:
            case Recalled(turns=turns):
                history, recalled = to_model_messages(turns), True
            case Unrecalled():
                history, recalled = [], False
            case _:
                assert_never(inp.history)
        notes = [run_context(ctx, self._clock())]
        if not recalled:
            notes.append(_LOST_CONTEXT_NOTE)
        # Finish inside the host's budget for this turn (None: no budget, no timeout).
        scope = asyncio.timeout(remaining())
        try:
            async with scope:
                result = await self._run(inp.text, history, deps, instructions="\n\n".join(notes))
        except TimeoutError:
            if not scope.expired():
                raise  # a TimeoutError from inside the run, not the budget
            logger.warning(
                "agent run out of time",
                extra={"user": hash_user_id(ctx.user.id, self._id_salt)},
            )
            _OUT_OF_TIME_RUNS.add(1)
            # Already in persona, and the budget is spent: no restyling pass, which could be
            # another model call.
            return SkillResult.message(_OUT_OF_TIME)
        self._log_outcome(result, ctx, recalled=recalled)
        card = next((a for a in reversed(deps.attachments) if a.embed is not None), None)
        files = tuple(f for a in deps.attachments for f in a.files)
        out = SkillResult.message(
            result.output,
            embed=card.embed if card is not None else None,
            files=files,
        )
        return await self._style.stylize(out, ctx)

    def _log_outcome(
        self, result: AgentRunResult[str], ctx: SkillContext, *, recalled: bool
    ) -> None:
        """Emit one metadata-only record per agent run: tools called, token usage, finish
        reason, and whether the reply context was recalled or lost. Independent of the trace
        backend, so it survives telemetry export being off or unavailable. No prompt, tags, or
        reply text; the only identifier is a salted hash. Also drives the tool-call /
        zero-tool / lost-context counters."""
        responses = [m for m in result.new_messages() if isinstance(m, ModelResponse)]
        tools = [p.tool_name for m in responses for p in m.parts if isinstance(p, ToolCallPart)]
        last = responses[-1] if responses else None
        usage = result.usage
        logger.info(
            "agent run",
            extra={
                "tools": tools,
                "tool_count": len(tools),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "requests": usage.requests,
                "finish_reason": last.finish_reason if last is not None else None,
                "model": last.model_name if last is not None else None,
                "output_len": len(result.output),
                "context": "recalled" if recalled else "unrecalled",
                "user": hash_user_id(ctx.user.id, self._id_salt),
            },
        )
        for tool in tools:
            _TOOL_CALLS.add(1, {"tool": tool})
        if not tools:
            _ZERO_TOOL_RUNS.add(1)
        if not recalled:
            _LOST_CONTEXT_RUNS.add(1)

    async def _run(
        self,
        prompt: str,
        history: list[ModelMessage],
        deps: ChatDeps,
        *,
        instructions: str | None = None,
    ) -> AgentRunResult[str]:
        """Run the agent, reactively compacting ``history`` if the model rejects it for
        length — the model's real window is the trigger, so we never guess a budget.

        On an overflow we compact and retry, up to :data:`MAX_COMPACTION_RETRIES` or until
        the history can no longer shrink; any other error (or a still-overflowing,
        un-shrinkable history) propagates to :func:`~petbot.platform.serve.serve`.
        """
        model = self._resolved_model()
        for attempt in range(MAX_COMPACTION_RETRIES + 1):
            try:
                return await self._agent.run(
                    prompt,
                    message_history=history,
                    deps=deps,
                    model=model,
                    model_settings=self._model_settings,
                    instructions=instructions,
                )
            except ModelHTTPError as exc:
                if not is_context_overflow(exc) or attempt == MAX_COMPACTION_RETRIES:
                    raise
                compacted = drop_leading_assistant(await self._compactor.compact(history))
                if len(compacted) >= len(history):
                    raise  # can't shrink further — give up rather than loop forever
                history = compacted
        raise AssertionError("unreachable: the loop returns or raises")  # pragma: no cover
