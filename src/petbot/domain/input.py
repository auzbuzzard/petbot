"""The neutral input to the pipeline — a discriminated sum type.

PetBot is ``input -> process -> output``. The input is *exactly one* of:

- a free-text message (an ``@mention``) the process must interpret, or
- a resolved command (a slash invocation) whose tool and arguments are already chosen.

Modelling it as a tagged union — not one model with optional fields — makes the
illegal states (both set, neither set) unrepresentable, and lets a
:class:`~petbot.domain.process.Process` dispatch on the variant with an exhaustive,
type-checked ``match``. The ``kind`` discriminator is what pydantic uses to
re-hydrate the right member from a wire payload.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field

from petbot.domain._model import Frozen


class TextInput(Frozen):
    """Free-text conversational input (an ``@mention``). The process interprets it."""

    kind: Literal["text"] = "text"
    text: str


class CommandInput(Frozen):
    """A resolved command (a slash invocation): the tool name and its raw arg values.

    ``values`` are *unvalidated* here — the compute service validates them against the named
    skill's ``args_model`` at the dispatch boundary, so this neutral input never
    needs to know any skill's argument shape.
    """

    kind: Literal["command"] = "command"
    name: str
    values: dict[str, object] = Field(default_factory=dict)


#: The pipeline input: exactly one variant, re-hydrated from a payload by ``kind``.
Input = Annotated[TextInput | CommandInput, Field(discriminator="kind")]
