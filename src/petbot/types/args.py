"""Per-skill argument models — the typed surface shared across packages.

Each ``*Args`` is a :class:`~petbot.domain._model.Frozen` pydantic model and is the
single source of truth for one skill's arguments: the skill implementation declares it
as ``args_model``, a :class:`~petbot.types.catalog.Command` carries it, the compute
service re-validates a wire payload against it, and the chat agent derives the LLM tool
schema from it. Defining them here — *without* the skill implementations — is what lets
the frontend build its slash surface with full types while keeping ``numexpr`` /
``yt-dlp`` / ``boto3`` out of the frontend.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from petbot.domain import Frozen

#: The music actions the skill understands.
MusicAction = Literal["play", "skip", "stop", "queue", "volume"]

#: What the ``leetcode`` skill looks up: today's daily problem, or a random one.
LeetCodeMode = Literal["daily", "random"]
#: LeetCode's three problem difficulties.
LeetCodeDifficulty = Literal["easy", "medium", "hard"]


class MathArgs(Frozen):
    """Arguments for the ``math`` skill."""

    # Field descriptions are the one source of per-argument help: they ride into the
    # LLM tool's json-schema *and* the Discord slash option descriptions.
    expression: str = Field(description="Arithmetic expression to evaluate.")


class BooruArgs(Frozen):
    """Arguments for a booru search (``derpi`` / ``e621``).

    The channel decides the safety floor (the frontend sets ``ctx.allows_explicit``
    from ``channel.is_nsfw()``), so there is no explicit *option* here. ``sort`` /
    ``file_type`` are provider tokens validated by the skill against that
    provider's native vocabulary.
    """

    tags: str = Field(description="Search tags, space-separated.")
    sort: str | None = Field(default=None, description="Provider sort token (e.g. score).")
    file_type: str | None = Field(default=None, description="Restrict to a file type.")
    min_score: int | None = Field(default=None, description="Minimum score floor.")
    descending: bool = Field(default=True, description="Highest-scoring first.")


class WebSearchArgs(Frozen):
    """Arguments for the ``web_search`` skill."""

    query: str = Field(description="What to search the web for, as a search-engine query.")


class WebFetchArgs(Frozen):
    """Arguments for the ``web_fetch`` skill."""

    url: str = Field(description="The full http(s) URL of the page to read.")


class WeatherArgs(Frozen):
    """Arguments for the ``weather`` skill."""

    location: str = Field(
        description="A place name, optionally with region or country (e.g. 'Paris, France')."
    )


class LeetCodeArgs(Frozen):
    """Arguments for the ``leetcode`` skill."""

    mode: LeetCodeMode | None = Field(
        default=None,
        description="'daily' for today's daily problem; 'random' for any other problem. With no "
        "mode, a difficulty means 'random' and no difficulty means 'daily'.",
    )
    difficulty: LeetCodeDifficulty | None = Field(
        default=None, description="For a random problem: only this difficulty."
    )

    @field_validator("mode", "difficulty", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        # Results spell difficulties LeetCode's way ("Easy"), which a model echoes back.
        return value.strip().lower() if isinstance(value, str) else value

    @property
    def effective_mode(self) -> LeetCodeMode:
        """The lookup asked for: a difficulty with no mode means a random problem."""
        if self.mode is not None:
            return self.mode
        return "random" if self.difficulty is not None else "daily"


class MusicArgs(Frozen):
    """Arguments for the ``music`` skill."""

    action: MusicAction
    query: str | None = None
    level: int | None = None
