"""The worker: discover installed skill plugins and run a dispatched call.

:meth:`Worker.run` is the single, typed skill-running core (used directly by an
in-process transport, with no serialisation). :meth:`Worker.serve` is the remote
boundary: it decodes a wire payload into a typed :class:`SkillCall` — validating
the args against the named skill's ``args_model`` — runs it, and encodes the
result back. A transport handler (an HTTP route, a Lambda handler) wraps
``serve``; the JSON lives only here and in the remote transports.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from importlib.metadata import entry_points
from typing import Any

from pydantic import BaseModel, ValidationError

from petbot.domain import Skill, SkillCall, SkillContext, SkillResult

logger = logging.getLogger(__name__)

#: The entry-point group every skill package registers under.
SKILLS_GROUP = "petbot.skills"

#: User-facing copy the worker surfaces at the dispatch boundary.
_SKILL_CRASHED = "Something went wrong running that skill."
_MALFORMED_REQUEST = "That request was malformed."


def _unknown_skill(name: str) -> str:
    return f"Unknown skill: `{name}`."


def _discover(group: str = SKILLS_GROUP) -> Iterator[Skill[Any]]:
    for ep in entry_points(group=group):
        target = ep.load()
        # An entry point is a Skill subclass, a build factory, or a ready
        # instance. The first two are callable; an instance is used as-is.
        skill = target() if callable(target) else target
        if not isinstance(skill, Skill):
            raise TypeError(f"Entry point {ep.name!r} is not a Skill: {skill!r}")
        yield skill


class Worker:
    """Runs the skill named in a :class:`SkillCall` against its installed plugins."""

    def __init__(self, skills: Iterable[Skill[Any]]) -> None:
        self._skills: dict[str, Skill[Any]] = {}
        for skill in skills:
            self._add(skill)

    def _add(self, skill: Skill[Any]) -> None:
        if skill.name in self._skills:
            raise ValueError(f"Duplicate skill name: {skill.name!r}")
        self._skills[skill.name] = skill

    @classmethod
    def from_installed_skills(cls) -> Worker:
        """Build a worker from the ``petbot.skills`` plugins installed here."""
        return cls(_discover())

    def register(self, skill: Skill[Any]) -> None:
        """Add a skill built with dependencies discovery can't supply (chat, music)."""
        self._add(skill)

    @property
    def skill_names(self) -> frozenset[str]:
        """The names of every skill this worker hosts."""
        return frozenset(self._skills)

    async def run(self, call: SkillCall) -> SkillResult:
        """Run ``call`` with its already-typed args — the in-process core.

        Unknown skills and skill exceptions become expected-failure results.
        """
        skill = self._skills.get(call.skill)
        if skill is None:
            logger.warning("Call for unknown skill: %r", call.skill)
            return SkillResult.failure(_unknown_skill(call.skill))
        try:
            return await skill.run(call.args, call.context)
        except Exception:
            logger.exception("Skill %r raised", call.skill)
            return SkillResult.failure(_SKILL_CRASHED)

    async def serve(self, body: str | bytes) -> str:
        """Remote boundary: decode a wire payload, run it, encode the result.

        The payload is ``{"skill": str, "args": {...}, "context": {...}}``; the
        args are validated against the named skill's ``args_model`` here, so the
        envelope never needs to know any skill's argument shape.
        """
        try:
            raw: dict[str, Any] = json.loads(body)
            name = raw["skill"]
            skill = self._skills.get(name)
            if skill is None:
                return SkillResult.failure(_unknown_skill(name)).model_dump_json()
            args: BaseModel = skill.args_model.model_validate(raw["args"])
            context = SkillContext.model_validate(raw["context"])
        except (ValueError, KeyError, ValidationError):
            # Bad JSON, missing fields, or args that fail validation — never let a
            # malformed payload escape the boundary; always return a result.
            logger.warning("Malformed dispatch payload", exc_info=True)
            return SkillResult.failure(_MALFORMED_REQUEST).model_dump_json()
        result = await self.run(SkillCall(skill=name, args=args, context=context))
        return result.model_dump_json()
