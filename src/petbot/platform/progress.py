"""Turn-progress signals from a transport to whoever is waiting on the turn.

A transport knows things its caller can't see, such as that the process it dispatches to
is still waking up. :func:`report` publishes the turn's current :class:`Phase`;
:func:`observe` subscribes a callback for the current context. It is a context variable, so
each concurrent turn sees only its own phases, and a caller that observes nothing (a slash
command, a test) pays nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from enum import StrEnum


class Phase(StrEnum):
    """Where a dispatched turn is."""

    #: The process isn't running yet (e.g. an ``Inactive`` Lambda re-pulling its image);
    #: the turn hasn't started.
    WAKING = "waking"
    #: The process is running the turn.
    THINKING = "thinking"


_observer: ContextVar[Callable[[Phase], None] | None] = ContextVar(
    "petbot_progress_observer", default=None
)


def report(phase: Phase) -> None:
    """Tell the current turn's observer, if any, that the turn is now in ``phase``."""
    observer = _observer.get()
    if observer is not None:
        observer(phase)


@contextmanager
def observe(callback: Callable[[Phase], None]) -> Iterator[None]:
    """Route :func:`report` calls to ``callback`` for work started inside this block.

    A task copies the context it is created in, so create the turn's task inside the block;
    it keeps reporting to ``callback`` after the block exits."""
    token = _observer.set(callback)
    try:
        yield
    finally:
        _observer.reset(token)
