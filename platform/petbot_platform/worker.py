"""The worker: discover installed skill plugins and run a dispatched request.

The inbound end of the A3a hop (edge -> remote DispatchPort -> worker). The
worker is the only side that runs skills; the edge never does. A transport
binding (a Lambda handler in the deploy bundle) deserialises the request with
``DispatchRequest.model_validate_json``, calls :meth:`Worker.handle`, and
serialises the result with ``result.model_dump_json`` — no separate wire layer.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from importlib.metadata import entry_points

from petbot_domain import DispatchRequest, Manifest, Skill, SkillResult

logger = logging.getLogger(__name__)

#: The entry-point group every skill package registers under.
SKILLS_GROUP = "petbot.skills"


def _discover(group: str = SKILLS_GROUP) -> Iterator[Skill]:
    for ep in entry_points(group=group):
        target = ep.load()
        skill = target() if isinstance(target, type) else target
        if not isinstance(skill, Skill):
            raise TypeError(f"Entry point {ep.name!r} is not a Skill: {skill!r}")
        yield skill


class Worker:
    """Runs the skill named in a dispatched request against its installed plugins."""

    def __init__(self, skills: Iterable[Skill]) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills:
            if skill.name in self._skills:
                raise ValueError(f"Duplicate skill name: {skill.name!r}")
            self._skills[skill.name] = skill

    @classmethod
    def from_installed_skills(cls) -> Worker:
        """Build a worker from the ``petbot.skills`` plugins installed here."""
        return cls(_discover())

    def manifest(self) -> Manifest:
        """The spec of every skill this worker hosts — for delivery to an edge."""
        return Manifest.of(self._skills.values())

    async def handle(self, request: DispatchRequest) -> SkillResult:
        """Run ``request.skill`` and return its result.

        Unknown skills and skill exceptions become expected-failure results, so a
        transport binding always has a result to serialise back.
        """
        skill = self._skills.get(request.skill)
        if skill is None:
            logger.warning("Dispatch for unknown skill: %r", request.skill)
            return SkillResult.failure(f"Unknown skill: `{request.skill}`.")
        try:
            return await skill.run(request.args, request.context)
        except Exception:
            logger.exception("Skill %r raised", request.skill)
            return SkillResult.failure("Something went wrong running that skill.")
