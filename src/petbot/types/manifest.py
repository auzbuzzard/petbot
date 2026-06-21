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
class CommandSpec[ArgsT: BaseModel]:
    """One dispatched skill, as data — the source both frontends derive from.

    Generic over its ``args_model`` so ``invoke`` is type-checked against the *same*
    model: a spec can dispatch only a skill that accepts its own args. This is *not*
    a second skill list — the :class:`~petbot.types.client.Skills` client lists every
    skill (``chat``/``music`` included, which are not commands); this is the curated
    *command* subset plus the user/LLM-facing copy a transport client doesn't carry.
    """

    name: str
    description: str
    args_model: type[ArgsT]
    #: Dispatch the (already-validated) args through a Skills client.
    invoke: Callable[[Skills, ArgsT, SkillContext], Awaitable[SkillResult]]


def _command[ArgsT: BaseModel](
    name: str,
    description: str,
    args_model: type[ArgsT],
    invoke: Callable[[Skills, ArgsT, SkillContext], Awaitable[SkillResult]],
) -> CommandSpec[ArgsT]:
    """Build a spec with its types tied together: mypy binds ``ArgsT`` from
    ``args_model``, then checks ``invoke`` against it — pairing ``BooruArgs`` with
    ``skills.math`` is a type error at the call site, not a runtime surprise."""
    return CommandSpec(name, description, args_model, invoke)


#: Every skill the edge exposes as a slash command and the chat agent offers as a
#: tool. Adding a skill here is the only edit either frontend needs. (Music is absent
#: by design — it lives on a separate worker, not the core the edge dispatches to.)
COMMANDS: tuple[CommandSpec[Any], ...] = (
    _command(
        "math",
        "Evaluate an arithmetic expression.",
        MathArgs,
        lambda skills, args, ctx: skills.math(args, ctx),
    ),
    _command(
        "derpi",
        "Search Derpibooru (My Little Pony imageboard) for an image.",
        BooruArgs,
        lambda skills, args, ctx: skills.derpi(args, ctx),
    ),
    _command(
        "e621",
        "Search e621 (furry imageboard) for an image.",
        BooruArgs,
        lambda skills, args, ctx: skills.e621(args, ctx),
    ),
)
