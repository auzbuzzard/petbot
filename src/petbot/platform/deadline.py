"""The time budget of the current turn.

The host that runs a turn knows how long it has (a Lambda invocation knows its remaining
time); the process doing the work doesn't. :func:`budget` sets the turn's deadline for work
started inside it, and :func:`remaining` reads what is left, so a process can finish with
an answer instead of being killed mid-run. It is a context variable, so concurrent turns
each see their own deadline, and a host that sets none (the dev server, tests) imposes none.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_deadline: ContextVar[float | None] = ContextVar("petbot_turn_deadline", default=None)


@contextmanager
def budget(seconds: float) -> Iterator[None]:
    """Give work started inside this block ``seconds`` to finish.

    A task copies the context it is created in, so create the turn's task inside the block.
    """
    token = _deadline.set(time.monotonic() + seconds)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining() -> float | None:
    deadline = _deadline.get()
    return None if deadline is None else max(0.0, deadline - time.monotonic())
