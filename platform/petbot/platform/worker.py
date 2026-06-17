"""The worker: discover installed skill plugins and run a dispatched call.

The inbound end of the A3a hop (edge -> ``Transport`` -> worker). The worker is
the only side that runs skills; the edge never does. :meth:`Worker.serve` is the
bytes-in/bytes-out binding a transport handler (an HTTP route, a Lambda handler)
wraps — it deserialises a :class:`~petbot.domain.call.SkillCall`, runs the named
skill, and serialises the :class:`~petbot.domain.result.SkillResult` back, all via
pydantic. No hand-rolled wire layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from importlib.metadata import entry_points
from typing import Any

from pydantic import BaseModel

from petbot.domain import Skill, SkillCall, SkillContext, SkillResult

logger = logging.getLogger(__name__)

#: The entry-point group every skill package registers under.
SKILLS_GROUP = "petbot.skills"


def _discover(group: str = SKILLS_GROUP) -> Iterator[Skill[Any]]:
    for ep in entry_points(group=group):
        target = ep.load()
        # An entry point is a Skill subclass, a build factory, or a ready
        # instance. The first two are callable (instantiate / build); an instance
        # is used as-is.
        skill = target() if callable(target) else target
        if not isinstance(skill, Skill):
            raise TypeError(f"Entry point {ep.name!r} is not a Skill: {skill!r}")
        yield skill


class Worker:
    """Runs the skill named in a :class:`SkillCall` against its installed plugins."""

    def __init__(self, skills: Iterable[Skill[Any]]) -> None:
        self._skills: dict[str, Skill[Any]] = {}
        for skill in skills:
            if skill.name in self._skills:
                raise ValueError(f"Duplicate skill name: {skill.name!r}")
            self._skills[skill.name] = skill

    @classmethod
    def from_installed_skills(cls) -> Worker:
        """Build a worker from the ``petbot.skills`` plugins installed here."""
        return cls(_discover())

    def register(self, skill: Skill[Any]) -> None:
        """Add a skill built with dependencies discovery can't supply (chat, music)."""
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    @property
    def skill_names(self) -> frozenset[str]:
        """The names of every skill this worker hosts."""
        return frozenset(self._skills)

    async def handle(self, call: SkillCall) -> SkillResult:
        """Re-hydrate ``call``'s typed args, run the skill, and return its result.

        Unknown skills and skill exceptions become expected-failure results, so a
        transport binding always has a result to serialise back.
        """
        skill = self._skills.get(call.skill)
        if skill is None:
            logger.warning("Call for unknown skill: %r", call.skill)
            return SkillResult.failure(f"Unknown skill: `{call.skill}`.")
        try:
            args = skill.args_model.model_validate_json(call.args_json)
            return await skill.run(args, call.context)
        except Exception:
            logger.exception("Skill %r raised", call.skill)
            return SkillResult.failure("Something went wrong running that skill.")

    async def serve(self, request_json: str | bytes) -> str:
        """Bytes-in/bytes-out binding: deserialise a call, run it, serialise the result."""
        return (await self.handle(SkillCall.model_validate_json(request_json))).model_dump_json()

    async def run_skill(self, name: str, args: BaseModel, ctx: SkillContext) -> SkillResult:
        """Run a hosted skill in-process with already-typed args (no JSON hop).

        Used by :class:`~petbot.platform.skills.LocalSkills` so the chat agent can
        call a sibling skill in the same worker without a needless wire round-trip.
        """
        skill = self._skills.get(name)
        if skill is None:
            return SkillResult.failure(f"Unknown skill: `{name}`.")
        return await skill.run(args, ctx)
