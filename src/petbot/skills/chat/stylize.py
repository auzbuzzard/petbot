"""The persona for the LLM-free path: text style transfer over a finished result.

A slash command dispatches a skill directly, with no chat agent to voice the reply,
so the worker restyles the neutral :class:`SkillResult` text into PetBot's voice
(``StylePort``). The ``@mention`` path needs none — the chat agent already voices its
own output, so its context leaves ``style_results`` ``False`` and the provider yields
no port. Implemented worker-side so the persona model never rides on the wire.
"""

from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models import Model

from petbot.domain import SkillContext, SkillResult, StylePort, StyleProvider
from petbot.skills.chat.model import build_model_from_config
from petbot.skills.chat.settings import ChatSettings


def _describe(result: SkillResult, ctx: SkillContext) -> str | None:
    """What the stylist is asked to voice, or ``None`` if there's nothing to say.

    A result with text carries a fact to relay (an empty-search reason); a result
    with only a card is a found image to greet over (the card is shown separately).
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
        if result.is_error:
            return result
        prompt = _describe(result, ctx)
        if prompt is None:
            return result
        styled = await self._agent.run(prompt, model=self._resolved_model())
        return result.model_copy(update={"text": styled.output})


class LLMStyleProvider(StyleProvider):
    """Hands the worker a :class:`Stylist` for requests that asked to be styled.

    Stateless across conversations (unlike a voice port), so one stylist serves every
    request; ``for_context`` simply gates on ``ctx.style_results``.
    """

    def __init__(self, settings: ChatSettings | None = None) -> None:
        self._stylist = Stylist(settings=settings or ChatSettings())

    def for_context(self, ctx: SkillContext) -> StylePort | None:
        return self._stylist if ctx.style_results else None
