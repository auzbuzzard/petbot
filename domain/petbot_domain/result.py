"""The neutral outcome of running a skill.

Rendering and length-chunking are the frontend's job, never the skill's — a
skill returns an ``EmbedSpec`` (a neutral card description), never a
platform-native embed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EmbedSpec:
    """A platform-neutral description of a rich card."""

    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    image_url: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_icon_url: str | None = None


@dataclass(frozen=True, slots=True)
class SkillResult:
    """A skill's neutral result: optional text, an optional card, files, an error.

    ``error`` carries *expected* failures (empty search, bad input) rendered as a
    friendly message — not exceptions.
    """

    text: str | None = None
    embed: EmbedSpec | None = None
    files: tuple[str, ...] = ()
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """Whether this result represents an expected failure."""
        return self.error is not None

    @classmethod
    def message(
        cls,
        text: str | None = None,
        *,
        embed: EmbedSpec | None = None,
        files: tuple[str, ...] = (),
    ) -> SkillResult:
        """Build a successful result."""
        return cls(text=text, embed=embed, files=files)

    @classmethod
    def failure(cls, error: str) -> SkillResult:
        """Build an expected-failure result (rendered as a friendly message)."""
        return cls(error=error)
