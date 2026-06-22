"""The neutral outcome of running a skill.

Rendering and length-chunking are the frontend's job, never the skill's — a
skill returns an :class:`EmbedSpec` (a neutral card description), never a
platform-native embed. Both types are :class:`~petbot.domain._model.Frozen`
pydantic models, so a result serialises itself back to the edge over the wire.
"""

from __future__ import annotations

from petbot.domain._model import Frozen


class EmbedSpec(Frozen):
    """A platform-neutral description of a rich card."""

    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    image_url: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_icon_url: str | None = None


class SkillResult(Frozen):
    """A skill's neutral result: optional text, an optional card, files.

    There is no error channel: an expected failure is **raised** as a
    :class:`~petbot.domain.errors.SkillError` and turned into a (voiced) result at the
    process output boundary — a result only ever describes an *answer*.
    """

    text: str | None = None
    embed: EmbedSpec | None = None
    files: tuple[str, ...] = ()

    @classmethod
    def message(
        cls,
        text: str | None = None,
        *,
        embed: EmbedSpec | None = None,
        files: tuple[str, ...] = (),
    ) -> SkillResult:
        """Build a result (optional text, an optional card, optional files)."""
        return cls(text=text, embed=embed, files=files)
