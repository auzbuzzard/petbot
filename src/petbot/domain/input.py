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

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import Field

from petbot.domain._model import Frozen


class Role(StrEnum):
    """Who spoke a :class:`Turn` — the structural position in the conversation.

    Neutral and platform-agnostic (it maps onto the user/assistant split every chat
    model uses); the speaker's *name* lives on :attr:`Turn.author`, not here.
    """

    USER = "user"
    ASSISTANT = "assistant"


class Turn(Frozen):
    """One prior message in the conversation a :class:`TextInput` continues.

    ``author`` is the speaker's display name (a user's, or — for an assistant turn —
    PetBot's own); ``text`` is what was said. An image-only bot reply is flattened to a
    faithful text description by the frontend, so ``text`` is never structured data.
    """

    role: Role
    author: str
    text: str


class TextInput(Frozen):
    """Free-text conversational input (an ``@mention``). The process interprets it.

    ``history`` is the prior turns of the conversation this message continues (the
    reply chain, oldest-first), reconstructed by the frontend; empty for a fresh
    @mention. It rides on the conversational variant — never on ``CommandInput`` — so a
    command can't carry chat history.
    """

    kind: Literal["text"] = "text"
    text: str
    history: tuple[Turn, ...] = ()


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
