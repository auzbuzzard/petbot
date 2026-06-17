"""``DispatchPort`` adapters — where a dispatched skill actually runs.

:class:`InProcessDispatch` runs the skill in the calling process against a local
registry. It is both the co-located/dev path and the worker-side executor behind
a remote dispatch adapter (Lambda/SQS), which land later.
"""

from __future__ import annotations

import logging

from petbot_domain import DispatchRequest, SkillResult
from petbot_platform.registry import SkillNotFoundError, SkillRegistry

logger = logging.getLogger(__name__)


class InProcessDispatch:
    """A :class:`~petbot_domain.DispatchPort` that runs skills in this process."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    async def dispatch(self, request: DispatchRequest) -> SkillResult:
        try:
            skill = self._registry.get(request.skill)
        except SkillNotFoundError:
            logger.warning("Dispatch for unknown skill: %r", request.skill)
            return SkillResult.failure(f"Unknown skill: `{request.skill}`.")
        return await skill.run(request.args, request.context)
