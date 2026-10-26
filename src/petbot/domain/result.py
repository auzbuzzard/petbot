"""The neutral outcome of running a skill.

Rendering and length-chunking are the frontend's job, never the skill's — a
skill returns an :class:`EmbedSpec` (a neutral card description), never a
platform-native embed. Both types are :class:`~petbot.domain._model.Frozen`
pydantic models, so a result serialises itself back to the frontend over the wire.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from petbot.domain._model import Frozen


class EmbedSpec(Frozen):
    title: str | None = None
    description: str | None = None
    url: str | None = None
    color: int | None = None
    image_url: str | None = None
    author_name: str | None = None
    author_url: str | None = None
    author_icon_url: str | None = None


class ToolCall(Frozen):
    """One tool call a process made while answering: the tool, the arguments it was called
    with, and what came back.

    ``outcome`` is ``returned`` when the tool ran and ``output`` is what it gave back (an
    expected failure's message included), ``rejected`` when the call never reached the tool
    and the model was asked to retry (``output`` says why), and ``unanswered`` when the turn
    ended before it was answered.
    """

    tool: str
    args: dict[str, object]
    outcome: Literal["returned", "rejected", "unanswered"]
    output: str | None = None


class SkillResult(Frozen):
    """A skill's neutral result: optional text, an optional card, files.

    There is no error channel: an expected failure is **raised** as a
    :class:`~petbot.domain.errors.SkillError` and turned into a (voiced) result at the
    process output boundary — a result only ever describes an *answer*.
    """

    text: str | None = None
    embed: EmbedSpec | None = None
    files: tuple[str, ...] = ()
    #: The tool calls behind this answer, for a test caller. ``None``, and left off the wire,
    #: unless the service is configured to report them. Frontends ignore it.
    trajectory: tuple[ToolCall, ...] | None = Field(default=None, exclude_if=lambda v: v is None)

    @classmethod
    def message(
        cls,
        text: str | None = None,
        *,
        embed: EmbedSpec | None = None,
        files: tuple[str, ...] = (),
    ) -> SkillResult:
        return cls(text=text, embed=embed, files=files)
