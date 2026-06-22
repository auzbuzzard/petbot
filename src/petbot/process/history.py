"""Map the neutral reply-chain history onto pydantic-ai message history.

The one place a conversation's prior turns — neutral :class:`~petbot.domain.input.Turn`
values, reconstructed frontend-side from the Discord reply chain — become model input. A
**pure** mapping: no model, no I/O, and no window management (an over-long history is
handled reactively in :mod:`petbot.process.context`, not by trimming here).
"""

from __future__ import annotations

from itertools import groupby
from typing import assert_never

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from petbot.domain import Role, Turn


def _content(turn: Turn) -> str:
    """The text a turn contributes, or ``""`` if it contributes nothing.

    A user turn is prefixed with its author so the model can attribute it in a
    multi-user chain; an assistant turn is not (the model owns its own replies).
    """
    text = turn.text.strip()
    if not text:
        return ""
    return f"{turn.author}: {text}" if turn.role is Role.USER else text


def drop_leading_assistant(messages: list[ModelMessage]) -> list[ModelMessage]:
    """Drop leading assistant messages so the history starts with a user message —
    providers reject an assistant-first run.

    Applied to a freshly-mapped history and again to a *compacted* one, since compaction
    can slice the leading user message off the front.
    """
    first_user = next(
        (i for i, message in enumerate(messages) if isinstance(message, ModelRequest)),
        len(messages),
    )
    return messages[first_user:]


def to_model_messages(history: tuple[Turn, ...]) -> list[ModelMessage]:
    """Turn the neutral ``history`` into pydantic-ai ``message_history``.

    Empty turns are dropped; consecutive same-role turns are merged (a multi-user chain
    produces them, and most backends reject a run of two of the same role); each is mapped
    by a role match; and any leading assistant message is dropped (the history must start
    with a user message).
    """
    pairs = [(turn.role, content) for turn in history if (content := _content(turn))]

    messages: list[ModelMessage] = []
    for role, group in groupby(pairs, key=lambda pair: pair[0]):
        content = "\n".join(text for _, text in group)
        match role:
            case Role.USER:
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            case Role.ASSISTANT:
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
            case _:
                assert_never(role)
    return drop_leading_assistant(messages)
