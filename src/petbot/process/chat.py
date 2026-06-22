"""The chat process: PetBot's conversational LLM brain — the first-class process.

``@mention`` input arrives as a :class:`~petbot.domain.input.TextInput`; this runs the
pydantic-ai agent over the message, letting it call tools (its sibling skills) through
the injected :class:`~petbot.platform.registry.ToolRegistry`, then folds the model's
prose plus any rich card a tool produced into one neutral
:class:`~petbot.domain.result.SkillResult`. The agent voices its own reply, so the
output ``StylePort`` is a no-op (:class:`~petbot.process.voice.PassthroughStyle`) —
styling stays uniform across processes without a second LLM pass.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from petbot.domain import Input, Process, SkillContext, SkillResult, StylePort, TextInput
from petbot.platform import ToolRegistry
from petbot.process.agent import ChatDeps, build_agent
from petbot.process.model import build_model
from petbot.process.settings import ChatSettings
from petbot.process.voice import PassthroughStyle


class ChatProcess(Process):
    """Talk to PetBot in natural language; it may call tools to answer."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
        style: StylePort | None = None,
    ) -> None:
        """Wire the agent.

        ``registry`` is the tools the agent dispatches to (in-process — no wire hop).
        ``model`` may be injected directly (e.g. a ``TestModel``); otherwise it is built
        lazily from ``settings`` on first use. ``style`` defaults to a no-op (the agent
        already voices its output).
        """
        self._registry = registry
        self._settings = settings or ChatSettings()
        self._model = model
        self._style: StylePort = style or PassthroughStyle()
        self._agent = build_agent(self._settings.system_prompt)

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model(self._settings)
        return self._model

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        if not isinstance(inp, TextInput):
            # The router only sends conversational input here; guard for type-safety.
            raise TypeError(f"ChatProcess received {type(inp).__name__}")
        deps = ChatDeps(registry=self._registry, ctx=ctx)
        result = await self._agent.run(inp.text, deps=deps, model=self._resolved_model())
        card = next((a for a in deps.attachments if a.embed is not None), None)
        files = tuple(f for a in deps.attachments for f in a.files)
        out = SkillResult.message(
            result.output,
            embed=card.embed if card is not None else None,
            files=files,
        )
        return await self._style.stylize(out, ctx)
