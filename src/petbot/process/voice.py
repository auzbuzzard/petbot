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

import logging
import re
import unicodedata

from pydantic_ai import Agent
from pydantic_ai.models import Model

from petbot.domain import SkillContext, SkillResult, StylePort
from petbot.process.model import build_model_from_config
from petbot.process.settings import ChatSettings

logger = logging.getLogger(__name__)

_MAX_NAME = 32

#: A fenced code block: formatted output (a math transcript) shown verbatim, never restated.
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def _shown_verbatim(text: str) -> bool:
    """Whether ``text`` is formatted output, shown as-is under a voiced line rather than
    restated: a fenced code block, or a result laid out over several lines (a LeetCode
    problem's fields), which a one-line restatement would flatten."""
    return bool(_FENCE.search(text)) or "\n" in text.strip()


#: The facts a restatement must keep word for word: links and numbers.
_FACT = re.compile(r"https?://\S+|\d+(?:[.,]\d+)*")


def addressee(ctx: SkillContext) -> str | None:
    printable = "".join(
        " " if ch.isspace() else ch
        for ch in ctx.user.display_name
        if ch.isspace() or not unicodedata.category(ch).startswith("C")
    )
    name = " ".join(printable.split())[:_MAX_NAME].strip()
    return name or None


def speaker_line(ctx: SkillContext) -> str:
    name = addressee(ctx)
    return f"You are talking with {name}." if name else "You don't know the user's name."


def _describe(result: SkillResult, ctx: SkillContext) -> str | None:
    """What the stylist is asked to voice, or ``None`` if there's nothing to say.

    A result with formatted output (see :func:`_shown_verbatim`) gets a one-line introduction
    only, since the output itself is shown verbatim beneath it. Other text is restated. A
    result with only a card is a found image to greet over (the card is shown separately).
    """
    if result.text and _shown_verbatim(result.text):
        return (
            f"{speaker_line(ctx)} This result is shown to them verbatim right below your "
            "line, so do not restate or summarise it; just introduce it."
            f"\n<result>\n{result.text}\n</result>"
        )
    if result.text:
        return f"{speaker_line(ctx)} Restate this result.\n<result>\n{result.text}\n</result>"
    if result.embed is not None:
        note = f"{speaker_line(ctx)} An image was found and is being shown to them."
        if ctx.allows_explicit:
            note += " The channel is age-gated (NSFW), so it may be explicit."
        return note
    return None


def _keeps_facts(original: str, restated: str) -> bool:
    return all(fact in restated for fact in _FACT.findall(original))


class Stylist(StylePort):
    def __init__(
        self,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
    ) -> None:
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
        """Voice ``result``. Formatted output keeps its text verbatim under a voiced line; a
        restatement that loses a number or link is discarded for the original text, since a
        correct answer beats an in-character wrong one."""
        prompt = _describe(result, ctx)
        if prompt is None:
            return result
        styled = (await self._agent.run(prompt, model=self._resolved_model())).output.strip()
        text = result.text
        if text and _shown_verbatim(text):
            return result.model_copy(update={"text": f"{styled}\n{text}"})
        if text and not _keeps_facts(text, styled):
            logger.warning("stylist dropped a fact from the result; sending it unstyled")
            return result
        return result.model_copy(update={"text": styled})


class PassthroughStyle(StylePort):
    async def stylize(self, result: SkillResult, ctx: SkillContext) -> SkillResult:
        return result
