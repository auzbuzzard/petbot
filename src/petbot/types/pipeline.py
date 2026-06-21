"""The one command pipeline: ``extract -> dispatch -> present``.

A command reaches a skill the same way no matter who sends it — a Discord slash
interaction, the chat agent's tool-loop, a future adapter. Only the *shapes* differ:
how the raw event yields ``(skills, ctx)`` (the input port), and how a neutral
:class:`~petbot.domain.result.SkillResult` becomes that frontend's output (the output
port). So the pipeline is written once here and each frontend injects its two ports;
nothing about discord.py or pydantic-ai leaks in. (An interaction additionally needs a
3-second-ack wrapper, but that is a frontend decorator around the handler, not part of
the pipeline.)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from petbot.domain import SkillContext, SkillResult
from petbot.types.client import Skills
from petbot.types.manifest import CommandSpec


async def dispatch_command(
    spec: CommandSpec[Any], skills: Skills, ctx: SkillContext, /, **values: object
) -> SkillResult:
    """The use case: validate raw ``values`` into the spec's args, then dispatch
    through the typed client. Frontend-agnostic — unit-testable with a fake
    ``Skills`` and no Discord/LLM types in sight."""
    return await spec.invoke(skills, spec.args_model(**values), ctx)


def command_handler[EventT, OutT](
    spec: CommandSpec[Any],
    *,
    extract: Callable[[EventT], tuple[Skills, SkillContext]],
    present: Callable[[EventT, SkillResult], Awaitable[OutT]],
    on_error: Callable[[EventT], SkillResult] | None = None,
) -> Callable[..., Awaitable[OutT]]:
    """Bind a catalog entry to a frontend by injecting its input/output ports.

    The body — extract, dispatch, present — is identical for every frontend; only
    the injected ports differ. ``present`` runs exactly once, *after* dispatch, so a
    friendly ``on_error`` result is rendered on the same path as a real one. With no
    ``on_error`` the dispatch failure propagates (the chat agent wants the raw error).
    """

    async def handle(event: EventT, /, **values: object) -> OutT:
        skills, ctx = extract(event)
        try:
            result = await dispatch_command(spec, skills, ctx, **values)
        except Exception:
            if on_error is None:
                raise
            result = on_error(event)
        return await present(event, result)

    return handle
