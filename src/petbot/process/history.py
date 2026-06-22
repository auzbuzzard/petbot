"""Map the neutral reply-chain history onto pydantic-ai message history.

The one place a conversation's prior turns — neutral :class:`~petbot.domain.input.Turn`
values, reconstructed frontend-side from the Discord reply chain — become model input. A
**pure** mapping: no model, no I/O, and no window management (an over-long history is
handled reactively in :mod:`petbot.process.context`, not by trimming here).
"""

from __future__ import annotations

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


def to_model_messages(history: tuple[Turn, ...]) -> list[ModelMessage]:
    """Turn the neutral ``history`` into pydantic-ai ``message_history``.

    Empty turns are dropped, then consecutive same-role turns are merged into one
    message (most chat backends reject a run of two user or two assistant messages, and
    a multi-user chain produces them), then each is mapped by an exhaustive role match.
    """
    pairs: list[tuple[Role, str]] = []
    for turn in history:
        content = _content(turn)
        if content:
            pairs.append((turn.role, content))

    merged: list[tuple[Role, str]] = []
    for role, content in pairs:
        if merged and merged[-1][0] == role:
            merged[-1] = (role, f"{merged[-1][1]}\n{content}")
        else:
            merged.append((role, content))

    messages: list[ModelMessage] = []
    for role, content in merged:
        match role:
            case Role.USER:
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            case Role.ASSISTANT:
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
            case _:
                assert_never(role)
    return messages
