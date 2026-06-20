"""The command manifest — every dispatched skill as data, in one place.

This is the single source the *frontends* derive their command surface from: the
chat agent registers one LLM tool per entry, and the Discord edge one slash command
per entry — both by looping :data:`COMMANDS`, neither hand-listing skills. A command
is ``(name, description, args_model, invoke)``:

* ``name`` / ``description`` — the user- and LLM-facing copy (slash name + help,
  tool name + description);
* ``args_model`` — the parameter schema. The slash options and the LLM tool schema
  are both *generated* from it, so the model stays the one source for arguments;
* ``invoke`` — dispatch the validated args through the typed
  :class:`~petbot.types.client.Skills` client.

It lives in the typed surface (not beside the skills) so the edge consumes it without
importing a skill — the dependency rule the architecture turns on.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from petbot.domain import SkillContext, SkillResult
from petbot.types.args import BooruArgs, MathArgs
from petbot.types.client import Skills


@dataclass(frozen=True)
class CommandSpec:
    """One dispatched skill, as data — the source both frontends derive from."""

    name: str
    description: str
    args_model: type[BaseModel]
    #: Dispatch the (already-validated) args through a Skills client.
    invoke: Callable[[Skills, Any, SkillContext], Awaitable[SkillResult]]


#: Every skill the edge exposes as a slash command and the chat agent offers as a
#: tool. Adding a skill here is the only edit either frontend needs. (Music is absent
#: by design — it lives on a separate worker, not the core the edge dispatches to.)
COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="math",
        description="Evaluate an arithmetic expression.",
        args_model=MathArgs,
        invoke=lambda skills, args, ctx: skills.math(args, ctx),
    ),
    CommandSpec(
        name="derpi",
        description="Search Derpibooru (My Little Pony imageboard) for an image.",
        args_model=BooruArgs,
        invoke=lambda skills, args, ctx: skills.derpi(args, ctx),
    ),
    CommandSpec(
        name="e621",
        description="Search e621 (furry imageboard) for an image.",
        args_model=BooruArgs,
        invoke=lambda skills, args, ctx: skills.e621(args, ctx),
    ),
)
