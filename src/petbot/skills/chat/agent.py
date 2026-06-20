"""The pydantic-ai agent: persona, dependency wiring, and sibling-skill tools.

Each sibling skill is exposed to the LLM as a typed tool whose argument is the
very same ``petbot.types`` ``*Args`` model the skill validates — so the tool
schema, the typed client call, and the worker's validation all share one source
of truth. Tool bodies dispatch through a :class:`petbot.types.Skills` client (a
``SkillsClient`` over a local transport in the core worker — an in-process hop,
no wire round trip). A tool that yields a rich card (a booru image) records it on
the deps so the chat skill can surface it alongside the model's prose.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext

from petbot.domain import SkillContext, SkillResult
from petbot.types import BooruArgs, MathArgs, Skills


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


def build_agent(system_prompt: str) -> Agent[ChatDeps, str]:
    """Build the chat agent with the sibling-skill tools registered.

    The model is bound per run (``agent.run(..., model=...)``) so the same agent
    object serves both the configured provider and ``TestModel`` in tests.
    """
    agent: Agent[ChatDeps, str] = Agent(
        deps_type=ChatDeps,
        output_type=str,
        # pydantic-ai 'instructions' (not 'system_prompt'): for a single agent it is
        # excluded from message history, and static instructions sort first so a
        # caching provider (Bedrock) can cache the stable prefix.
        instructions=system_prompt,
    )

    @agent.tool
    async def math(ctx: RunContext[ChatDeps], args: MathArgs) -> str:
        """Evaluate an arithmetic expression."""
        return _summarise(ctx.deps, await ctx.deps.skills.math(args, ctx.deps.ctx))

    @agent.tool
    async def derpi(ctx: RunContext[ChatDeps], args: BooruArgs) -> str:
        """Search Derpibooru (My Little Pony imageboard) for an image."""
        return _summarise(ctx.deps, await ctx.deps.skills.derpi(args, ctx.deps.ctx))

    @agent.tool
    async def e621(ctx: RunContext[ChatDeps], args: BooruArgs) -> str:
        """Search e621 (furry imageboard) for an image."""
        return _summarise(ctx.deps, await ctx.deps.skills.e621(args, ctx.deps.ctx))

    return agent
