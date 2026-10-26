from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from petbot.domain import Frozen

MusicAction = Literal["play", "skip", "stop", "queue", "volume"]

LeetCodeMode = Literal["daily", "random"]
LeetCodeDifficulty = Literal["easy", "medium", "hard"]


class MathArgs(Frozen):
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
    query: str = Field(description="What to search the web for, as a search-engine query.")


class WebFetchArgs(Frozen):
    url: str = Field(description="The full http(s) URL of the page to read.")


class WeatherArgs(Frozen):
    location: str = Field(
        description="A place name, optionally with region or country (e.g. 'Paris, France')."
    )


class LeetCodeArgs(Frozen):
    mode: LeetCodeMode = Field(
        description="'daily' for today's daily problem; 'random' for any other problem."
    )
    difficulty: LeetCodeDifficulty | None = Field(
        default=None, description="For a random problem: only this difficulty."
    )

    @field_validator("mode", "difficulty", mode="before")
    @classmethod
    def _lowercase(cls, value: object) -> object:
        return value.strip().lower() if isinstance(value, str) else value


class MusicArgs(Frozen):
    action: MusicAction
    query: str | None = None
    level: int | None = None
