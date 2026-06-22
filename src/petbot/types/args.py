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

from pydantic import Field

from petbot.domain import Frozen

#: The music actions the skill understands.
MusicAction = Literal["play", "skip", "stop", "queue", "volume"]


class MathArgs(Frozen):
    """Arguments for the ``math`` skill."""

    # Field descriptions are the one source of per-argument help: they ride into the
    # LLM tool's json-schema *and* the Discord slash option descriptions.
    expression: str = Field(description="Arithmetic expression to evaluate.")


class BooruArgs(Frozen):
    """Arguments for a booru search (``derpi`` / ``e621``).

    The channel decides the safety floor (the edge sets ``ctx.allows_explicit``
    from ``channel.is_nsfw()``), so there is no explicit *option* here. ``sort`` /
    ``file_type`` are provider tokens validated by the skill against that
    provider's native vocabulary.
    """

    tags: str = Field(description="Search tags, space-separated.")
    sort: str | None = Field(default=None, description="Provider sort token (e.g. score).")
    file_type: str | None = Field(default=None, description="Restrict to a file type.")
    min_score: int | None = Field(default=None, description="Minimum score floor.")
    descending: bool = Field(default=True, description="Highest-scoring first.")


class MusicArgs(Frozen):
    """Arguments for the ``music`` skill."""

    action: MusicAction
    query: str | None = None
    level: int | None = None
