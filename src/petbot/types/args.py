"""Per-skill argument models — the typed surface shared across packages.

Each ``*Args`` is a :class:`~petbot.domain._model.Frozen` pydantic model and is
the single source of truth for one skill's arguments: the skill implementation
declares it as ``args_model``, the typed :class:`~petbot.types.client.Skills`
client takes it as a parameter, the worker re-validates the wire payload against
it, and the chat agent derives the LLM tool schema from it. Defining them here —
*without* the skill implementations — is what lets the edge call skills with
full types while keeping ``numexpr`` / ``yt-dlp`` / ``boto3`` out of the edge.
"""

from __future__ import annotations

from typing import Literal

from petbot.domain import Frozen

#: The music actions the skill understands.
MusicAction = Literal["play", "skip", "stop", "queue", "volume"]


class MathArgs(Frozen):
    """Arguments for the ``math`` skill."""

    expression: str


class BooruArgs(Frozen):
    """Arguments for a booru search (``derpi`` / ``e621``).

    The channel decides the safety floor (the edge sets ``ctx.allows_explicit``
    from ``channel.is_nsfw()``), so there is no explicit *option* here. ``sort`` /
    ``file_type`` are provider tokens validated by the skill against that
    provider's native vocabulary.
    """

    tags: str
    sort: str | None = None
    file_type: str | None = None
    min_score: int | None = None
    descending: bool = True


class MusicArgs(Frozen):
    """Arguments for the ``music`` skill."""

    action: MusicAction
    query: str | None = None
    level: int | None = None


class ChatArgs(Frozen):
    """Arguments for the ``chat`` skill (the conversational LLM entrypoint)."""

    message: str
