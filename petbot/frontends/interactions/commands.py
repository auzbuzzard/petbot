"""Slash-command definitions for the HTTP-Interactions app.

Discord stores slash commands **per application**, not per transport, and the
interactions Lambda only *handles* commands at request time (see
:mod:`.handler`) — it never registers them. This module is that missing piece:
the single, declarative source of truth for what :mod:`.register` PUTs to
Discord.

It is deliberately ``discord``-free — plain dicts in Discord's
application-command schema (``CHAT_INPUT`` type, numeric option types) — so it
stays importable on the minimal Lambda runtime and obeys the same core/adapter
import boundary as the rest of ``petbot.frontends.interactions`` (enforced by
import-linter).

Each entry mirrors what :class:`~petbot.frontends.interactions.handler.InteractionHandler`
dispatches: one command per interactions-available skill (``/math``, ``/derpi``,
``/e621``), plus the adapter-level ``/ping``. Option ``name`` keys match the keys
each skill reads from ``args`` and the properties of its ``input_schema``; the
``tests/test_interactions_commands.py`` guardrail fails if the two ever drift.
``/music`` is absent because it requires the voice capability the interactions
frontend does not advertise; ``/purge`` is not yet wired on this path.
"""

from __future__ import annotations

from typing import Any, Final

# Discord application-command type (only chat-input/slash commands here).
# https://discord.com/developers/docs/interactions/application-commands
CHAT_INPUT: Final = 1

# Application-command option types we use.
_STRING: Final = 3
_INTEGER: Final = 4
_BOOLEAN: Final = 5

# NOTE: Discord requires every required option to precede the optional ones; the
# guardrail test enforces this ordering so a reorder can't silently break the PUT.
COMMANDS: Final[list[dict[str, Any]]] = [
    {
        "type": CHAT_INPUT,
        "name": "ping",
        "description": "Liveness check.",
        "options": [],
    },
    {
        "type": CHAT_INPUT,
        "name": "math",
        "description": "Evaluate a mathematical expression.",
        "options": [
            {
                "type": _STRING,
                "name": "expression",
                "description": "The arithmetic expression to evaluate, e.g. '2 * 21'.",
                "required": True,
            },
        ],
    },
    {
        "type": CHAT_INPUT,
        "name": "derpi",
        "description": "Search Derpibooru for an image.",
        "options": [
            {
                "type": _STRING,
                "name": "tags",
                "description": "Comma-separated tags (spaces allowed within a tag).",
                "required": True,
            },
            {
                "type": _STRING,
                "name": "sort",
                "description": "How to order matches before picking one.",
            },
            {
                "type": _BOOLEAN,
                "name": "descending",
                "description": "Sort descending (default) or ascending.",
            },
            {
                "type": _STRING,
                "name": "file_type",
                "description": "Restrict results to a file type.",
            },
            {
                "type": _INTEGER,
                "name": "min_score",
                "description": "Only results with at least this score.",
            },
        ],
    },
    {
        "type": CHAT_INPUT,
        "name": "e621",
        "description": "Search e621 for an image.",
        "options": [
            {
                "type": _STRING,
                "name": "tags",
                "description": "Space-separated tags (use underscores within a tag).",
                "required": True,
            },
            {
                "type": _STRING,
                "name": "sort",
                "description": "How to order matches before picking one.",
            },
            {
                "type": _STRING,
                "name": "file_type",
                "description": "Restrict results to a file type.",
            },
            {
                "type": _INTEGER,
                "name": "min_score",
                "description": "Only results with at least this score.",
            },
        ],
    },
]
