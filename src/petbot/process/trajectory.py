"""An agent run's tool calls as :class:`~petbot.domain.result.ToolCall` records: the
trajectory a regression test grades, read from the run's own messages."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
    ToolReturnPart,
)

from petbot.domain import ToolCall


def trajectory(messages: Sequence[ModelMessage]) -> tuple[ToolCall, ...]:
    """Each tool call in ``messages``, in order, with what the model got back for it."""
    answers: dict[str, ToolReturnPart | RetryPromptPart] = {
        part.tool_call_id: part
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart | RetryPromptPart)
    }
    calls: list[ToolCall] = []
    for message in messages:
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if not isinstance(part, ToolCallPart):
                continue
            answer = answers.get(part.tool_call_id)
            args = dict(part.args_as_dict())
            if isinstance(answer, ToolReturnPart):
                call = ToolCall(
                    tool=part.tool_name,
                    args=args,
                    outcome="returned",
                    output=answer.model_response_str(),
                )
            elif isinstance(answer, RetryPromptPart):
                call = ToolCall(
                    tool=part.tool_name,
                    args=args,
                    outcome="rejected",
                    output=answer.model_response(),
                )
            else:
                call = ToolCall(tool=part.tool_name, args=args, outcome="unanswered")
            calls.append(call)
    return tuple(calls)
