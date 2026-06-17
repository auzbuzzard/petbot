"""The worker: runs a dispatched request against its installed skills.

This is the *inbound* end of the edge -> worker hop. A transport binding (e.g. a
Lambda handler in the deploy bundle) deserialises the request with
:mod:`.wire`, calls :meth:`Worker.handle`, and serialises the result back. The
worker is the only side that runs skills — the edge never does.
"""

from __future__ import annotations

import logging

from petbot_domain import DispatchRequest, SkillResult
from petbot_platform.loader import build_registry
from petbot_platform.registry import SkillNotFoundError, SkillRegistry

logger = logging.getLogger(__name__)


class Worker:
    """Runs a skill named in a :class:`DispatchRequest` against a local registry."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    @classmethod
    def from_installed_skills(cls) -> Worker:
        """Build a worker from the ``petbot.skills`` plugins installed here."""
        return cls(build_registry())

    async def handle(self, request: DispatchRequest) -> SkillResult:
        """Run ``request.skill`` and return its result.

        Unknown skills and skill exceptions become expected-failure results, so a
        transport binding always has a ``SkillResult`` to serialise back.
        """
        try:
            skill = self._registry.get(request.skill)
        except SkillNotFoundError:
            logger.warning("Dispatch for unknown skill: %r", request.skill)
            return SkillResult.failure(f"Unknown skill: `{request.skill}`.")
        try:
            return await skill.run(request.args, request.context)
        except Exception:
            logger.exception("Skill %r raised", request.skill)
            return SkillResult.failure("Something went wrong running that skill.")
