"""The pydantic-ai agent: persona, dependency wiring, and catalog-driven tools.

Each entry in :data:`petbot.types.CATALOG` becomes one LLM tool: its schema is the
skill's own ``args_model`` and its body dispatches through the per-request
:class:`~petbot.platform.registry.ToolRegistry` (an in-process call, no wire hop). So
the tool schema, the registry's validation, and the frontend's slash command all share
one declaration; the agent hand-lists no skill. A tool that yields a rich card (a booru
image) records it on the deps so the chat process can surface it with the model's prose.
A tool's expected failure surfaces to the model as a short note, not a crash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, RunContext, Tool
from pydantic_ai.capabilities import Instrumentation
from pydantic_ai.models.instrumented import InstrumentationSettings

from petbot.domain import SkillContext, SkillError, SkillResult
from petbot.platform import ToolRegistry
from petbot.types import CATALOG, Command


@dataclass
class ChatDeps:
    """Per-request dependencies handed to every tool."""

    registry: ToolRegistry
    ctx: SkillContext
    #: Rich results (a booru image card) captured by tools, surfaced in the reply.
    attachments: list[SkillResult] = field(default_factory=list)


def _summarise(deps: ChatDeps, result: SkillResult) -> str:
    """Turn a tool's :class:`SkillResult` into a short string for the LLM, and capture
    any rich card so the chat process can attach it to the final reply."""
    if result.embed is not None or result.files:
        deps.attachments.append(result)
    parts: list[str] = []
    if result.text:
        parts.append(result.text)
    if result.embed is not None and result.embed.image_url:
        parts.append(f"(image attached: {result.embed.image_url})")
    return "\n".join(parts) or "Done."


def _tool_for(spec: Command[Any]) -> Tool[ChatDeps]:
    """Build one LLM tool from a catalog entry. Its body validates+runs the tool through
    the registry; an expected :class:`SkillError` is reported back to the model."""

    async def run(ctx: RunContext[ChatDeps], **values: Any) -> str:
        deps = ctx.deps
        try:
            result = await deps.registry.dispatch(spec.name, values, deps.ctx)
        except SkillError as exc:
            return f"The skill reported: {exc.message}"
        return _summarise(deps, result)

    return Tool.from_schema(
        run,
        name=spec.name,
        description=spec.description,
        json_schema=spec.args_model.model_json_schema(),
        takes_ctx=True,
    )


def build_agent(
    system_prompt: str,
    *,
    instrumentation: InstrumentationSettings | None = None,
) -> Agent[ChatDeps, str]:
    """Build the chat agent with one tool per :data:`~petbot.types.CATALOG` entry.

    Adding a skill to the catalog adds its tool here for free — no per-skill code. The
    model is bound per run (``agent.run(..., model=...)``) so the same agent serves both
    the configured provider and ``TestModel`` in tests.

    When ``instrumentation`` is given (built by the composition root from the global
    OpenTelemetry providers, with ``include_content=False``), pydantic-ai emits the agent
    run / model request / tool spans + token-usage metrics. ``None`` ⇒ no instrumentation,
    so dev and tests stay quiet.
    """
    capabilities = (
        [Instrumentation(settings=instrumentation)] if instrumentation is not None else []
    )
    return Agent(
        deps_type=ChatDeps,
        output_type=str,
        # pydantic-ai 'instructions' (not 'system_prompt'): for a single agent it is
        # excluded from message history, and static instructions sort first so a
        # caching provider (Bedrock) can cache the stable prefix.
        instructions=system_prompt,
        tools=[_tool_for(spec) for spec in CATALOG],
        capabilities=capabilities,
    )
