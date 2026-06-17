"""The chat skill: the conversational LLM entrypoint.

Runs the pydantic-ai agent over the user's message, letting it call sibling
skills as tools, then folds the model's prose plus any rich card a tool produced
into a single neutral :class:`SkillResult`.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from petbot.domain import Skill, SkillContext, SkillResult
from petbot.skills.chat.agent import ChatDeps, build_agent
from petbot.skills.chat.model import build_model
from petbot.skills.chat.settings import ChatSettings
from petbot.types import ChatArgs, Skills


class ChatSkill(Skill[ChatArgs]):
    """Talk to PetBot in natural language; it may call other skills as tools."""

    name = "chat"
    description = "Have a natural conversation with PetBot (may use other skills)."
    args_model = ChatArgs

    def __init__(
        self,
        skills: Skills,
        *,
        model: Model | str | None = None,
        settings: ChatSettings | None = None,
    ) -> None:
        """Wire the agent.

        ``skills`` is the client tools dispatch through (a ``SkillsClient`` in the
        core worker). ``model`` may be injected directly (e.g. a ``TestModel``);
        otherwise it is built lazily from ``settings`` on first use.
        """
        self._skills = skills
        self._settings = settings or ChatSettings()
        self._model = model
        self._agent = build_agent()

    def _resolved_model(self) -> Model | str:
        if self._model is None:
            self._model = build_model(self._settings)
        return self._model

    async def run(self, args: ChatArgs, ctx: SkillContext) -> SkillResult:
        deps = ChatDeps(skills=self._skills, ctx=ctx)
        result = await self._agent.run(args.message, deps=deps, model=self._resolved_model())
        card = next((a for a in deps.attachments if a.embed is not None), None)
        files = tuple(f for a in deps.attachments for f in a.files)
        return SkillResult.message(
            result.output,
            embed=card.embed if card is not None else None,
            files=files,
        )
