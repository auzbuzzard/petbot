"""The Discord slash-command frontend: catalog -> app commands, over the gateway.

Each entry in :data:`petbot.types.COMMANDS` becomes one slash command. The runtime
body is *not* written here — it is the shared :func:`petbot.types.command_handler`
pipeline, into which this module injects the edge's two ports (``extract``: an
interaction -> ``skills`` + neutral context; ``present``: :func:`respond_interaction`)
plus its friendly-failure policy. The interaction's 3-second ack rule is the one
edge-specific wrapper (:func:`_with_defer`). The only irreducible per-frontend code is
:func:`_as_app_command`, which renders a skill's ``args_model`` into discord.py options.

Like the rest of the edge it imports the typed surface and the args models — never a
skill, so the always-on holder still carries no skill dependency.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from inspect import Parameter, Signature
from typing import Any

import discord
from discord import app_commands

from petbot.domain import SkillContext, SkillResult
from petbot.edge.context import build_interaction_context
from petbot.edge.render import WORKER_UNREACHABLE, respond_interaction
from petbot.types import COMMANDS, CommandSpec, Skills, command_handler

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


def _friendly_failure(_interaction: discord.Interaction) -> SkillResult:
    """Map a dispatch failure to a friendly result (logged with traceback — this is
    called from inside the handler's ``except`` block)."""
    logger.exception("slash dispatch failed")
    return SkillResult.failure(WORKER_UNREACHABLE)


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


def _as_app_command(
    spec: CommandSpec[Any], callback: Callable[..., Awaitable[None]]
) -> app_commands.Command[Any, ..., None]:
    """Render ``spec``'s ``args_model`` into a discord.py command: one option per
    field, its type/required-ness read off the model and its help off the field's
    description (via the public :func:`app_commands.describe`, not a private attr).

    discord.py builds the options by introspecting the callback's signature, so we
    attach a schema-bearing signature to the real ``**values`` callback explicitly.
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


def build_commands(skills: Skills) -> list[app_commands.Command[Any, ..., None]]:
    """One slash command per catalog entry, all riding the shared pipeline. Call
    once ``skills`` is wired (in ``setup_hook``); the closure captures it."""

    def extract(interaction: discord.Interaction) -> tuple[Skills, SkillContext]:
        return skills, build_interaction_context(interaction)

    commands: list[app_commands.Command[Any, ..., None]] = []
    for spec in COMMANDS:
        handle = command_handler(
            spec, extract=extract, present=respond_interaction, on_error=_friendly_failure
        )
        commands.append(_as_app_command(spec, _with_defer(handle)))
    return commands
