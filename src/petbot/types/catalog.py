"""The command catalog — every slash/tool command as one typed entry.

This is the single source both *consumers* derive their command surface from: the
Discord frontend builds one slash command per entry, and the chat agent offers one LLM
tool per entry — neither hand-lists skills. A :class:`Command` is pure data —
``(name, description, args_model)``:

* ``name`` / ``description`` — the user- and LLM-facing copy (slash name + help, tool
  name + description);
* ``args_model`` — the parameter schema. The slash options and the LLM tool schema are
  both *generated* from it, and a dispatched ``CommandInput``'s raw values are validated
  against it — so the model stays the one source for arguments.

It lives in the typed surface (not beside the skills) so a frontend consumes it without
importing a skill — the dependency rule the architecture turns on. (Chat is **not** a
command — it is the conversational process. Music is absent by design — it lives on a
separate compute service, not the core the frontend dispatches to.)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from petbot.types.args import BooruArgs, MathArgs


@dataclass(frozen=True)
class Command[ArgsT: BaseModel]:
    """One command, as data — the source both the slash surface and the agent derive from.

    Generic over its ``args_model`` so the argument type is carried with the entry and
    every derivation (slash options, tool schema, dispatch validation) stays typed
    against the *same* model.
    """

    name: str
    description: str
    args_model: type[ArgsT]


#: Every skill the frontend exposes as a slash command and the chat agent offers as a
#: tool. Adding a skill here is the only edit either consumer needs.
CATALOG: tuple[Command[Any], ...] = (
    Command("math", "Evaluate an arithmetic expression.", MathArgs),
    Command("derpi", "Search Derpibooru (My Little Pony imageboard) for an image.", BooruArgs),
    Command("e621", "Search e621 (furry imageboard) for an image.", BooruArgs),
)
