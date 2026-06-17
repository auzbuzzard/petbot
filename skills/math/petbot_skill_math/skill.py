"""PetBot math skill — evaluate an arithmetic expression with ``numexpr``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import numexpr

from petbot_domain import Skill, SkillContext, SkillResult

logger = logging.getLogger(__name__)


def _evaluate(expression: str) -> Any:
    """Evaluate ``expression`` with numexpr and return a plain Python scalar.

    ``numexpr`` only understands a restricted arithmetic grammar, which keeps this
    far safer than ``eval``. Runs in a worker thread (see :meth:`MathSkill.run`) so
    it never blocks the event loop.
    """
    return numexpr.evaluate(expression).item()


class MathSkill(Skill):
    """Evaluate a mathematical expression like ``2 * 21`` or ``sqrt(144)``."""

    name = "math"
    description = "Evaluate a mathematical expression."
    input_schema: Mapping[str, Any] = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "The arithmetic expression to evaluate, e.g. '2 * 21'.",
            },
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        expression = str(args["expression"]).strip()
        try:
            result: Any = await asyncio.to_thread(_evaluate, expression)
        except Exception as exc:
            # The error is the *output* (shown in the same code block), not an
            # exceptional failure — the result goes straight to the user.
            logger.debug("math: %r could not be evaluated: %s", expression, exc)
            return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{exc}\n```")
        return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{result}\n```")
