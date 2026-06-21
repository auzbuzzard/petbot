"""The pydantic-ai agent: persona, dependency wiring, and manifest-driven tools.

Each entry in :data:`petbot.types.COMMANDS` becomes one LLM tool: its schema is the
skill's own ``args_model`` and its body dispatches through a
:class:`petbot.types.Skills` client (a ``SkillsClient`` over a local transport in the
core worker — an in-process hop, no wire round trip). So the tool schema, the typed
client call, the worker's validation, and the edge's slash command all share one
declaration; the agent hand-lists no skill. A tool that yields a rich card (a booru
image) records it on the deps so the chat skill can surface it with the model's prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext, Tool

from petbot.domain import SkillContext, SkillResult
from petbot.types import COMMANDS, CommandSpec, Skills, command_handler


@dataclass
class ChatDeps:
    """Per-request dependencies handed to every tool."""

    skills: Skills
    ctx: SkillContext
    #: Rich results (a booru image card) captured by tools, surfaced in the reply.
    attachments: list[SkillResult] = field(default_factory=list)


def _summarise(deps: ChatDeps, result: SkillResult) -> str:
    """Turn a sibling :class:`SkillResult` into a short string for the LLM, and
    capture any rich card so the chat skill can attach it to the final reply."""
    if result.is_error:
        return f"The skill reported: {result.error}"
    if result.embed is not None or result.files:
        deps.attachments.append(result)
    parts: list[str] = []
    if result.text:
        parts.append(result.text)
    if result.embed is not None and result.embed.image_url:
        parts.append(f"(image attached: {result.embed.image_url})")
    return "\n".join(parts) or "Done."


async def _present(ctx: RunContext[ChatDeps], result: SkillResult) -> str:
    """The LLM output port: a coroutine wrapper over the sync :func:`_summarise`."""
    return _summarise(ctx.deps, result)


def _tool_for(spec: CommandSpec[Any]) -> Tool[ChatDeps]:
    """Build one LLM tool from a catalog entry on the shared command pipeline. The
    LLM's two ports: ``extract`` reads ``skills``/``ctx`` off the run's deps, and
    ``present`` summarises the result back to the model (capturing any rich card).
    No ``on_error`` — a tool failure surfaces to the model as an error, not a crash.
    """
    handle = command_handler(
        spec,
        extract=lambda ctx: (ctx.deps.skills, ctx.deps.ctx),
        present=_present,
    )
    return Tool.from_schema(
        handle,
        name=spec.name,
        description=spec.description,
        json_schema=spec.args_model.model_json_schema(),
        takes_ctx=True,
    )


def build_agent(system_prompt: str) -> Agent[ChatDeps, str]:
    """Build the chat agent with one tool per :data:`~petbot.types.COMMANDS` entry.

    Adding a skill to the manifest adds its tool here for free — no per-skill code.
    The model is bound per run (``agent.run(..., model=...)``) so the same agent
    serves both the configured provider and ``TestModel`` in tests.
    """
    return Agent(
        deps_type=ChatDeps,
        output_type=str,
        system_prompt=system_prompt,
        tools=[_tool_for(spec) for spec in COMMANDS],
    )
