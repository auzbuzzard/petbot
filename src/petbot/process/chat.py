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

from typing import assert_never

from pydantic_ai import AgentRunResult
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models import Model

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
from petbot.platform import ToolRegistry
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

#: Per-run instruction added to PetBot's persona when a reply's prior context couldn't be
#: read (``Unrecalled``), so the agent voices that it lost the thread instead of guessing.
_LOST_CONTEXT_NOTE = (
    "The user is replying to earlier messages you can no longer see. If their message "
    "relies on that lost context, tell them you've lost the thread and ask them to recap; "
    "otherwise just answer normally."
)


class ChatProcess(Process):
    """Talk to PetBot in natural language; it may call tools to answer."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
        style: StylePort | None = None,
    ) -> None:
        """Wire the agent.

        ``registry`` is the tools the agent dispatches to (in-process — no wire hop).
        ``model`` may be injected directly (e.g. a ``TestModel``); otherwise it is built
        lazily from ``settings`` on first use. ``style`` defaults to a no-op (the agent
        already voices its output).
        """
        self._registry = registry
        self._settings = settings or ChatSettings()
        self._model = model
        self._style: StylePort = style or PassthroughStyle()
        self._agent = build_agent(self._settings.system_prompt)
        self._compactor: Compactor = build_compactor(self._settings, model=model)

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model(self._settings)
        return self._model

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        if not isinstance(inp, TextInput):
            # The router only sends conversational input here; guard for type-safety.
            raise TypeError(f"ChatProcess received {type(inp).__name__}")
        deps = ChatDeps(registry=self._registry, ctx=ctx)
        match inp.history:
            case Recalled(turns=turns):
                history, note = to_model_messages(turns), None
            case Unrecalled():
                # Replied to context we couldn't read: no history, and tell the agent so it
                # voices that it lost the thread rather than answering blind.
                history, note = [], _LOST_CONTEXT_NOTE
            case _:
                assert_never(inp.history)
        result = await self._run(inp.text, history, deps, instructions=note)
        card = next((a for a in deps.attachments if a.embed is not None), None)
        files = tuple(f for a in deps.attachments for f in a.files)
        out = SkillResult.message(
            result.output,
            embed=card.embed if card is not None else None,
            files=files,
        )
        return await self._style.stylize(out, ctx)

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
