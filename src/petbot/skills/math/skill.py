from __future__ import annotations

import ast
import asyncio
import logging
import math
import operator
from collections.abc import Callable

from petbot.domain import Skill, SkillContext, SkillResult
from petbot.types import MathArgs

logger = logging.getLogger(__name__)

type Number = int | float | complex

MAX_EXPRESSION_LENGTH = 256
MAX_INT_BITS = 1024


def _sign(x: float) -> float:
    return type(x)((x > 0) - (x < 0))


_FUNCTIONS: dict[str, tuple[Callable[..., Number], int]] = {
    "sqrt": (math.sqrt, 1),
    "sin": (math.sin, 1),
    "cos": (math.cos, 1),
    "tan": (math.tan, 1),
    "arcsin": (math.asin, 1),
    "arccos": (math.acos, 1),
    "arctan": (math.atan, 1),
    "arctan2": (math.atan2, 2),
    "sinh": (math.sinh, 1),
    "cosh": (math.cosh, 1),
    "tanh": (math.tanh, 1),
    "arcsinh": (math.asinh, 1),
    "arccosh": (math.acosh, 1),
    "arctanh": (math.atanh, 1),
    "log": (math.log, 1),
    "log10": (math.log10, 1),
    "log2": (math.log2, 1),
    "log1p": (math.log1p, 1),
    "exp": (math.exp, 1),
    "expm1": (math.expm1, 1),
    "hypot": (math.hypot, 2),
    "fmod": (math.fmod, 2),
    "copysign": (math.copysign, 2),
    "nextafter": (math.nextafter, 2),
    "abs": (abs, 1),
    "ceil": (lambda x: float(math.ceil(x)), 1),
    "floor": (lambda x: float(math.floor(x)), 1),
    "trunc": (lambda x: float(math.trunc(x)), 1),
    "round": (lambda x: float(round(x)), 1),
    "sign": (_sign, 1),
    "maximum": (max, 2),
    "minimum": (min, 2),
}

_BINARY: dict[type[ast.operator], Callable[[Number, Number], Number]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
}

_UNARY: dict[type[ast.unaryop], Callable[[Number], Number]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class _Rejected(ValueError):
    pass


def _check_size(value: Number) -> Number:
    if isinstance(value, int) and value.bit_length() > MAX_INT_BITS:
        raise _Rejected("result is too large")
    return value


def _power(base: Number, exponent: Number) -> Number:
    # Refuse an integer power whose result would exceed the cap before computing it.
    if (
        isinstance(base, int)
        and isinstance(exponent, int)
        and exponent > 0
        and abs(base) > 1
        and (abs(base).bit_length() - 1) * exponent > MAX_INT_BITS
    ):
        raise _Rejected("result is too large")
    return base**exponent


def _eval(node: ast.AST) -> Number:
    match node:
        case ast.Expression(body=body):
            return _eval(body)
        case ast.Constant(value=value) if isinstance(
            value, int | float | complex
        ) and not isinstance(value, bool):
            return _check_size(value)
        case ast.UnaryOp(op=op, operand=operand) if type(op) in _UNARY:
            return _UNARY[type(op)](_eval(operand))
        case ast.BinOp(left=left, op=ast.Pow(), right=right):
            return _check_size(_power(_eval(left), _eval(right)))
        case ast.BinOp(left=left, op=op, right=right) if type(op) in _BINARY:
            return _check_size(_BINARY[type(op)](_eval(left), _eval(right)))
        case ast.Call(func=ast.Name(id=name), args=args, keywords=keywords) if name in _FUNCTIONS:
            function, arity = _FUNCTIONS[name]
            if keywords or len(args) != arity:
                raise _Rejected(f"{name}() takes {arity} argument{'s' if arity > 1 else ''}")
            return _check_size(function(*(_eval(arg) for arg in args)))
        case ast.Call(func=ast.Name(id=name)):
            raise _Rejected(f"unknown function {name!r}")
        case ast.Name(id=name):
            raise _Rejected(f"unknown name {name!r}")
        case _:
            raise _Rejected("unsupported expression")


def evaluate(expression: str) -> Number:
    """Evaluate an arithmetic ``expression``, allowing only numbers, operators and math functions.

    The expression is parsed, never executed: anything outside the allowlist in
    :func:`_eval` is rejected, and integer results are capped at ``MAX_INT_BITS``.
    """
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise _Rejected(f"expression is longer than {MAX_EXPRESSION_LENGTH} characters")
    return _eval(ast.parse(expression, mode="eval"))


class MathSkill(Skill[MathArgs]):
    """Evaluate a mathematical expression like ``2 * 21`` or ``sqrt(144)``."""

    name = "math"
    description = "Evaluate a mathematical expression."
    args_model = MathArgs

    async def run(self, args: MathArgs, ctx: SkillContext) -> SkillResult:
        expression = args.expression.strip()
        try:
            result = await asyncio.to_thread(evaluate, expression)
        except Exception as exc:
            logger.debug("math: %r could not be evaluated: %s", expression, exc)
            return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{exc}\n```")
        return SkillResult.message(f"```py\n>>>\t{expression}\n<<<\t{result}\n```")
