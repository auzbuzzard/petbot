"""The math skill: safely evaluate an arithmetic expression with ``numexpr``."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import numexpr

from petbot.domain import Skill, SkillContext, SkillResult
from petbot.types import MathArgs

logger = logging.getLogger(__name__)


def _evaluate(expression: str) -> Any:
    """Evaluate ``expression`` with numexpr and return a plain Python scalar.

    ``numexpr`` only understands a restricted arithmetic grammar, which keeps this
    far safer than ``eval``. Runs in a worker thread (see :meth:`MathSkill.run`)
    so it never blocks the event loop.
    """
    return numexpr.evaluate(expression).item()


class MathSkill(Skill[MathArgs]):
    """Evaluate a mathematical expression like ``2 * 21`` or ``sqrt(144)``."""

    name = "math"
    description = "Evaluate a mathematical expression."
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        expression = args.expression.strip()
        try:
            result: Any = await asyncio.to_thread(_evaluate, expression)
        except Exception as exc:
            # Legacy behaviour: the error is the *output*, shown in the same code
            # block, not an exceptional failure.
            logger.debug("math: %r could not be evaluated: %s", expression, exc)
            return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{exc}\n```")
        return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{result}\n```")
