"""The persona voice — a :class:`~petbot.domain.ports.StylePort`, two implementations.

Styling is a *uniform output stage*: every process runs its result through a
``StylePort``. Which one is dependency-injected:

* :class:`Stylist` — the command path (a slash command, no LLM in the loop) rewrites the
  result's text into PetBot's voice with a small, tool-less LLM call. An error message is
  voiced the same way (it arrives as a result with text). Implemented compute-side so the
  persona model never rides on the wire.
* :class:`PassthroughStyle` — the chat path: the agent already voiced its output, so this
  no-op keeps the stage uniform without a second LLM pass.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models import Model

from petbot.domain import SkillContext, SkillResult, StylePort
from petbot.process.model import build_model_from_config
from petbot.process.settings import ChatSettings


def _describe(result: SkillResult, ctx: SkillContext) -> str | None:
    """What the stylist is asked to voice, or ``None`` if there's nothing to say.

    A result with text carries a line to relay (an answer, or a voiced failure note); a
    result with only a card is a found image to greet over (the card is shown separately).
    """
    if result.text:
        return result.text
    if result.embed is not None:
        note = "An image was found and is being shown to the user."
        if ctx.allows_explicit:
            note += " The channel is age-gated (NSFW), so it may be explicit."
        return note
    return None


class Stylist(StylePort):
    """Rewrites a result's text in PetBot's voice with a small, tool-less LLM call."""

    def __init__(
        self,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
    ) -> None:
        """``model`` may be injected directly (a ``TestModel``); otherwise it is built
        lazily from the stylizer config (:meth:`ChatSettings.stylizer_llm`)."""
        self._settings = settings or ChatSettings()
        self._model = model
        self._agent: Agent[None, str] = Agent(
            output_type=str, instructions=self._settings.stylizer_prompt
        )

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model_from_config(self._settings.stylizer_llm())
        return self._model

    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult:
        prompt = _describe(result, ctx)
        if prompt is None:
            return result
        styled = await self._agent.run(prompt, model=self._resolved_model())
        return result.model_copy(update={"text": styled.output})


class PassthroughStyle(StylePort):
    """A no-op ``StylePort``: the result is already voiced (the chat agent voiced it)."""

    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult:
        return result
