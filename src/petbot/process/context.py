"""Reactive context-window handling: compact history only when the model rejects it.

pydantic-ai does not expose a model's context-window *size*
(https://redirect.github.com/pydantic/pydantic-ai/issues/4538), so PetBot does **not**
guess a token budget — a budget constant would be wrong the moment the configured model
is swapped. Instead the *provider* is the trigger: a run is attempted, and only if it
fails for length (:func:`is_context_overflow`) does the chat process compact the message
history and retry.

The strategy is dependency-injected from :class:`~petbot.process.settings.ChatSettings`
via :func:`build_compactor` (a config ``match``, like
:func:`~petbot.process.model.build_model_from_config`): a :class:`SlidingWindow` (drop the
oldest half, zero cost) or a :class:`Summarizer` (one small-LLM pass over the oldest
half). Proactive, precise budgeting can drop in behind the same seam once the window size
is exposed upstream.
"""

from __future__ import annotations

from typing import Protocol, assert_never

from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart
from pydantic_ai.models import Model

from petbot.process.model import build_model_from_config
from petbot.process.settings import (
    ChatSettings,
    SlidingWindowContext,
    SummarizeContext,
)

#: How many times to compact-and-retry before giving up on an over-long conversation.
MAX_COMPACTION_RETRIES = 3

#: HTTP statuses a provider uses to reject an over-long request.
_OVERFLOW_STATUS = frozenset({400, 413})
#: Phrases providers put in the body of a context-length rejection (lower-cased).
_OVERFLOW_PHRASES = (
    "context length",
    "context window",
    "maximum context",
    "too long",
    "too many tokens",
    "reduce the length",
    "string too long",
)

_SUMMARIZE_INSTRUCTIONS = (
    "Summarise the earlier conversation concisely for use as context in an ongoing chat. "
    "Preserve facts, names, decisions, and anything the user might refer back to; omit "
    "small talk. Write the summary as plain notes, not a reply."
)


def is_context_overflow(exc: Exception) -> bool:
    """Best-effort: does ``exc`` look like a provider rejecting an over-long request?

    Provider-specific — pydantic-ai surfaces it as a :class:`ModelHTTPError` with no
    typed "context length exceeded", so we match a 400/413 whose text names a length
    limit. A false negative just means we don't retry; a false positive costs one
    needless compaction.
    """
    if not isinstance(exc, ModelHTTPError) or exc.status_code not in _OVERFLOW_STATUS:
        return False
    text = str(exc).lower()
    return any(phrase in text for phrase in _OVERFLOW_PHRASES)


class Compactor(Protocol):
    """Shrinks an over-long message history so a retried run can fit."""

    async def compact(self, messages: list[ModelMessage]) -> list[ModelMessage]:
        """Return a shorter history; return it unchanged if it can't be shortened."""
        ...


class SlidingWindow:
    """Drop the oldest half of the history. Zero cost — old turns are simply forgotten."""

    async def compact(self, messages: list[ModelMessage]) -> list[ModelMessage]:
        if len(messages) <= 1:
            return messages
        return messages[len(messages) // 2 :]


class Summarizer:
    """Replace the oldest half of the history with a small-LLM summary of it.

    Mirrors the :class:`~petbot.process.voice.Stylist` pattern: a small, tool-less agent
    whose model is the cheaper stylizer tier (:meth:`ChatSettings.stylizer_llm`), built
    lazily so construction stays offline and a ``TestModel`` can be injected.
    """

    def __init__(
        self,
        *,
        settings: ChatSettings | None = None,
        model: Model | str | None = None,
    ) -> None:
        self._settings = settings or ChatSettings()
        self._model = model
        self._agent: Agent[None, str] = Agent(output_type=str, instructions=_SUMMARIZE_INSTRUCTIONS)

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model_from_config(self._settings.stylizer_llm())
        return self._model

    async def compact(self, messages: list[ModelMessage]) -> list[ModelMessage]:
        if len(messages) <= 2:
            return messages
        split = len(messages) // 2
        older, recent = messages[:split], messages[split:]
        summary = await self._agent.run(message_history=older, model=self._resolved_model())
        note = ModelRequest(
            parts=[UserPromptPart(content=f"[Summary of earlier conversation]\n{summary.output}")]
        )
        return [note, *recent]


def build_compactor(
    settings: ChatSettings,
    *,
    model: Model | str | None = None,
) -> Compactor:
    """Build the configured compaction strategy (a config ``match``, like the model).

    ``model`` is forwarded to the summarizer (``None`` ⇒ it lazily builds the stylizer
    tier); the sliding window ignores it.
    """
    match settings.context:
        case SlidingWindowContext():
            return SlidingWindow()
        case SummarizeContext():
            return Summarizer(settings=settings, model=model)
        case _:
            assert_never(settings.context)
