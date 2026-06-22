"""The Discord slash-command frontend: catalog -> app commands, over the gateway.

Each entry in :data:`petbot.types.CATALOG` becomes one slash command whose body builds a
:class:`~petbot.domain.input.CommandInput` and dispatches it through the injected
:class:`~petbot.domain.process.Process` (a :class:`~petbot.platform.ProcessClient`). The
interaction's 3-second-ack rule is the one frontend-specific wrapper
(:func:`_with_defer`); :func:`_as_app_command` renders a skill's ``args_model`` into
discord.py options. Like the rest of the frontend it imports the typed catalog and the
args models — never a skill.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from inspect import Parameter, Signature
from typing import Any

import discord
from discord import app_commands

from petbot.domain import CommandInput, Process, SkillResult
from petbot.frontends.discord.context import build_interaction_context
from petbot.frontends.discord.render import WORKER_UNREACHABLE, respond_interaction
from petbot.types import CATALOG, Command

logger = logging.getLogger(__name__)

#: The option value types Discord can express. A skill arg of any other type would
#: need an explicit mapping here, so we fail loud rather than ship a broken command.
_OPTION_TYPES: dict[type, type] = {str: str, int: int, bool: bool, float: float}


def _option_type(annotation: object) -> type:
    """The type discord.py should see for one option. Unwraps ``X | None`` (an
    optional option) to its real member; raises on a type Discord can't express."""
    base = annotation
    args = getattr(annotation, "__args__", ())
    if args:
        base = next(arg for arg in args if arg is not type(None))
    if base not in _OPTION_TYPES:
        raise TypeError(f"slash options can't express {annotation!r}")
    return _OPTION_TYPES[base]


def _with_defer(
    handle: Callable[..., Awaitable[None]],
) -> Callable[..., Awaitable[None]]:
    """Wrap a handler with the one interaction-specific rule: acknowledge within
    Discord's 3-second window (a Lambda cold start can exceed it) before dispatching,
    so the real answer can arrive later as a followup."""

    async def guarded(interaction: discord.Interaction, **values: object) -> None:
        await interaction.response.defer()
        await handle(interaction, **values)

    return guarded


def _make_handler(process: Process, spec: Command[Any]) -> Callable[..., Awaitable[None]]:
    """The runtime body of one slash command: build a CommandInput, dispatch, render.

    A transport failure is the one error rendered here (the styler is unreachable);
    every expected failure is already voiced into the result by the process."""

    async def handle(interaction: discord.Interaction, **values: object) -> None:
        ctx = build_interaction_context(interaction)
        try:
            result = await process.respond(CommandInput(name=spec.name, values=values), ctx)
        except Exception:
            logger.exception("slash dispatch failed")
            result = SkillResult.message(WORKER_UNREACHABLE)
        await respond_interaction(interaction, result)

    return handle


def _as_app_command(
    spec: Command[Any], callback: Callable[..., Awaitable[None]]
) -> app_commands.Command[Any, ..., None]:
    """Render ``spec``'s ``args_model`` into a discord.py command: one option per field,
    its type/required-ness read off the model and its help off the field's description
    (via the public :func:`app_commands.describe`, not a private attr).

    discord.py builds the options by introspecting the callback's signature, so we attach
    a schema-bearing signature to the real ``**values`` callback explicitly.
    """
    params = [
        Parameter("interaction", Parameter.POSITIONAL_OR_KEYWORD, annotation=discord.Interaction)
    ]
    descriptions: dict[str, str] = {}
    for name, field in spec.args_model.model_fields.items():
        default = Parameter.empty if field.is_required() else field.default
        params.append(
            Parameter(
                name,
                Parameter.POSITIONAL_OR_KEYWORD,
                annotation=_option_type(field.annotation),
                default=default,
            )
        )
        if field.description:
            descriptions[name] = field.description
    callback.__signature__ = Signature(params)  # type: ignore[attr-defined]
    if descriptions:
        callback = app_commands.describe(**descriptions)(callback)
    # The callback is dynamically signed (the `**values` body wears a synthesized
    # signature), so its static type can't match discord.py's callback protocol —
    # the boundary this whole adapter exists to bridge.
    return app_commands.Command(
        name=spec.name,
        description=spec.description,
        callback=callback,  # type: ignore[arg-type]
    )


def build_commands(process: Process) -> list[app_commands.Command[Any, ..., None]]:
    """One slash command per catalog entry, all dispatching through ``process``. Call
    once the process client is wired (in ``setup_hook``); the closure captures it."""
    commands: list[app_commands.Command[Any, ..., None]] = []
    for spec in CATALOG:
        handle = _with_defer(_make_handler(process, spec))
        commands.append(_as_app_command(spec, handle))
    return commands
