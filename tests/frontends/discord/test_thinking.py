"""The thinking state: typing for the whole turn, pausing at each checkpoint; never a message.

Each test runs on an event loop with a virtual clock: a wait that would block jumps the
clock forward instead, so the real timings (10 s checkpoint, 5 s refresh, 2 s pause) run
instantly and every trigger lands at an exact time, independent of the OS timer's
granularity.
"""

from __future__ import annotations

import asyncio
import selectors
from collections.abc import Coroutine
from itertools import pairwise
from typing import Any

import discord
import pytest

from petbot.frontends.discord.thinking import (
    PAUSE_SECONDS,
    TYPING_LIFETIME_SECONDS,
    TYPING_REFRESH_SECONDS,
    think,
)
from petbot.platform import Phase, report


class _InstantSelector(selectors.DefaultSelector):
    """A selector that never blocks: a ``select`` that would wait ``timeout`` seconds
    advances :attr:`now` by that much and returns at once."""

    def __init__(self) -> None:
        super().__init__()
        self.now = 0.0

    def select(self, timeout: float | None = None) -> list[tuple[selectors.SelectorKey, int]]:
        if timeout is None:
            raise RuntimeError("the loop is waiting on nothing that can ever finish")
        self.now += timeout
        return super().select(0)


class _VirtualTimeLoop(asyncio.SelectorEventLoop):
    def __init__(self) -> None:
        self._clock = _InstantSelector()
        super().__init__(self._clock)

    def time(self) -> float:
        return self._clock.now


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion in virtual time, then let leftover tasks (the cancelled
    typing loop) finish, so none is destroyed pending."""

    async def main() -> T:
        result = await coro
        me = asyncio.current_task()
        leftover = [task for task in asyncio.all_tasks() if task is not me]
        await asyncio.gather(*leftover, return_exceptions=True)
        return result

    loop = _VirtualTimeLoop()
    try:
        return loop.run_until_complete(main())
    finally:
        loop.close()


class _FakeResp:
    status = 403
    reason = "Forbidden"


class _FakeChannel:
    """Records when typing was triggered. Has no ``send``: the thinking state never posts."""

    def __init__(self, *, typing_error: Exception | None = None) -> None:
        self.triggers: list[float] = []
        self._typing_error = typing_error

    async def typing(self) -> None:
        # `await channel.typing()` is one trigger in discord.py.
        self.triggers.append(asyncio.get_running_loop().time())
        if self._typing_error is not None:
            raise self._typing_error


class _FakeMessage:
    """Has no ``reply``: the thinking state never posts a placeholder."""

    def __init__(self, channel: _FakeChannel | None = None) -> None:
        self.channel = channel or _FakeChannel()


def _gaps(triggers: list[float]) -> list[float]:
    return [b - a for a, b in pairwise(triggers)]


def _pauses(triggers: list[float]) -> int:
    # A pause is a gap long enough for the last trigger to lapse and the pause to show.
    return sum(gap >= TYPING_LIFETIME_SECONDS + PAUSE_SECONDS for gap in _gaps(triggers))


async def _answer(delay: float) -> str:
    await asyncio.sleep(delay)
    return "answer"


def test_quick_turn_types_once_and_never_pauses() -> None:
    message = _FakeMessage()
    assert _run(think(message, _answer(1))) == "answer"  # type: ignore[arg-type]
    assert message.channel.triggers == [0.0]


def test_long_turn_keeps_typing_and_pauses_at_the_checkpoint() -> None:
    message = _FakeMessage()
    # The 12 s checkpoint lands between refreshes (0, 5, 10), so the last trigger has 8 s
    # left to lapse, then the 2 s pause: typing resumes at 22 s and refreshes until 40 s.
    assert _run(think(message, _answer(40), after=12)) == "answer"  # type: ignore[arg-type]
    assert message.channel.triggers == pytest.approx([0, 5, 10, 22, 27, 32, 37])
    assert _pauses(message.channel.triggers) == 1


async def _wakes_then_answers() -> str:
    # What the Lambda transport reports for an Inactive worker: waking, then running.
    await asyncio.sleep(1)
    report(Phase.WAKING)
    await asyncio.sleep(29)
    report(Phase.THINKING)
    await asyncio.sleep(20)
    return "answer"


def test_each_reported_phase_is_a_checkpoint() -> None:
    message = _FakeMessage()
    result = _run(think(message, _wakes_then_answers(), after=1000))  # type: ignore[arg-type]
    assert result == "answer"
    # WAKING (1 s) and THINKING (30 s) each pause typing once; the checkpoint is never reached.
    assert message.channel.triggers == pytest.approx([0, 12, 17, 22, 27, 39, 44, 49])
    assert _pauses(message.channel.triggers) == 2


def test_checkpoints_during_a_pause_share_it() -> None:
    async def phases_back_to_back() -> str:
        await asyncio.sleep(1)
        report(Phase.WAKING)
        await asyncio.sleep(1)
        report(Phase.THINKING)
        await asyncio.sleep(38)
        return "answer"

    message = _FakeMessage()
    _run(think(message, phases_back_to_back(), after=1000))  # type: ignore[arg-type]
    assert message.channel.triggers == pytest.approx([0, 12, 17, 22, 27, 32, 37])
    assert _pauses(message.channel.triggers) == 1


@pytest.mark.parametrize(
    "error",
    [discord.Forbidden(_FakeResp(), "Missing Permissions"), OSError("connection reset")],  # type: ignore[arg-type]
)
def test_typing_failures_never_sink_the_turn(error: Exception) -> None:
    message = _FakeMessage(_FakeChannel(typing_error=error))
    assert _run(think(message, _answer(20), after=12)) == "answer"  # type: ignore[arg-type]
    assert message.channel.triggers == pytest.approx([0, 5, 10])


def test_a_failed_turn_raises_and_stops_typing() -> None:
    async def boom() -> str:
        await asyncio.sleep(3)
        raise RuntimeError("kaboom")

    message = _FakeMessage()

    async def scenario() -> tuple[int, int]:
        with pytest.raises(RuntimeError):
            await think(message, boom())  # type: ignore[arg-type]
        count = len(message.channel.triggers)
        await asyncio.sleep(TYPING_REFRESH_SECONDS * 3)
        return count, len(message.channel.triggers)

    before, after = _run(scenario())
    assert before == after == 1
