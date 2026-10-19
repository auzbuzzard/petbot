"""The thinking state: typing for the whole turn, pausing at each checkpoint; never a message."""

from __future__ import annotations

import asyncio
import time
from itertools import pairwise

import discord
import pytest

from petbot.frontends.discord import thinking
from petbot.frontends.discord.thinking import think
from petbot.platform import Phase, report

#: Scaled-down timings: one trigger "lasts" 50 ms, refreshes every 20 ms, pauses for 40 ms.
_LIFETIME, _REFRESH, _PAUSE = 0.05, 0.02, 0.04


@pytest.fixture(autouse=True)
def _fast_typing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(thinking, "TYPING_LIFETIME_SECONDS", _LIFETIME)
    monkeypatch.setattr(thinking, "TYPING_REFRESH_SECONDS", _REFRESH)
    monkeypatch.setattr(thinking, "PAUSE_SECONDS", _PAUSE)


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
        self.triggers.append(time.monotonic())
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
    return sum(gap >= _LIFETIME + _PAUSE * 0.8 for gap in _gaps(triggers))


async def _answer(delay: float) -> str:
    await asyncio.sleep(delay)
    return "answer"


async def test_quick_turn_types_once_and_never_pauses() -> None:
    message = _FakeMessage()
    assert await think(message, _answer(0.01), after=1) == "answer"  # type: ignore[arg-type]
    assert len(message.channel.triggers) == 1


async def test_long_turn_keeps_typing_and_pauses_at_the_checkpoint() -> None:
    message = _FakeMessage()
    assert await think(message, _answer(0.4), after=0.03) == "answer"  # type: ignore[arg-type]
    triggers = message.channel.triggers
    # One pause, then typing resumes (a trigger after the pause) and keeps refreshing.
    assert _pauses(triggers) == 1
    resumed = next(i for i, gap in enumerate(_gaps(triggers)) if gap >= _LIFETIME)
    assert len(triggers) > resumed + 2


async def _wakes_then_answers() -> str:
    # What the Lambda transport reports for an Inactive worker: waking, then running.
    await asyncio.sleep(0.01)
    report(Phase.WAKING)
    await asyncio.sleep(0.2)
    report(Phase.THINKING)
    await asyncio.sleep(0.2)
    return "answer"


async def test_each_reported_phase_is_a_checkpoint() -> None:
    message = _FakeMessage()
    result = await think(message, _wakes_then_answers(), after=10)  # type: ignore[arg-type]
    assert result == "answer"
    # WAKING and THINKING each pause typing once; the 10 s mark is never reached.
    assert _pauses(message.channel.triggers) == 2


async def test_checkpoints_during_a_pause_share_it() -> None:
    async def phases_back_to_back() -> str:
        await asyncio.sleep(0.01)
        report(Phase.WAKING)
        await asyncio.sleep(0.01)
        report(Phase.THINKING)
        await asyncio.sleep(0.3)
        return "answer"

    message = _FakeMessage()
    await think(message, phases_back_to_back(), after=10)  # type: ignore[arg-type]
    assert _pauses(message.channel.triggers) == 1


@pytest.mark.parametrize(
    "error",
    [discord.Forbidden(_FakeResp(), "Missing Permissions"), OSError("connection reset")],  # type: ignore[arg-type]
)
async def test_typing_failures_never_sink_the_turn(error: Exception) -> None:
    message = _FakeMessage(_FakeChannel(typing_error=error))
    assert await think(message, _answer(0.1), after=0.03) == "answer"  # type: ignore[arg-type]
    assert message.channel.triggers  # it kept trying


async def test_a_failed_turn_raises_and_stops_typing() -> None:
    async def boom() -> str:
        await asyncio.sleep(0.05)
        raise RuntimeError("kaboom")

    message = _FakeMessage()
    with pytest.raises(RuntimeError):
        await think(message, boom(), after=10)  # type: ignore[arg-type]
    count = len(message.channel.triggers)
    await asyncio.sleep(_REFRESH * 3)
    assert len(message.channel.triggers) == count  # the typing loop is gone
