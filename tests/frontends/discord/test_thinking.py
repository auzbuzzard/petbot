"""The thinking state: typing for every turn, a placeholder only for a slow one."""

from __future__ import annotations

import asyncio
from typing import Any

import discord
import pytest

from petbot.frontends.discord.thinking import THINKING, clear, think


class _FakeResp:
    status = 403
    reason = "Forbidden"


class _Typing:
    """``channel.typing()``: an async context manager that is also awaitable (one trigger)."""

    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel

    async def __aenter__(self) -> None:
        self._channel.events.append("typing:start")

    async def __aexit__(self, *exc: object) -> None:
        self._channel.events.append("typing:stop")

    def __await__(self) -> Any:
        async def trigger() -> None:
            self._channel.events.append("typing:trigger")

        return trigger().__await__()


class _FakeChannel:
    def __init__(self) -> None:
        self.events: list[str] = []

    def typing(self) -> _Typing:
        return _Typing(self)


class _FakePlaceholder:
    def __init__(self, channel: _FakeChannel) -> None:
        self._channel = channel

    async def delete(self) -> None:
        self._channel.events.append("placeholder:delete")


class _FakeMessage:
    def __init__(self, *, reply_fails: bool = False) -> None:
        self.channel = _FakeChannel()
        self._reply_fails = reply_fails
        self.reply_kwargs: dict[str, Any] = {}

    async def reply(self, content: str, **kwargs: Any) -> _FakePlaceholder:
        if self._reply_fails:
            raise discord.Forbidden(_FakeResp(), "Missing Permissions")  # type: ignore[arg-type]
        self.channel.events.append(f"reply:{content}")
        self.reply_kwargs = kwargs
        return _FakePlaceholder(self.channel)


async def _answer(delay: float) -> str:
    await asyncio.sleep(delay)
    return "answer"


async def test_quick_turn_only_types() -> None:
    message = _FakeMessage()
    result, placeholder = await think(message, _answer(0), after=1)  # type: ignore[arg-type]
    assert (result, placeholder) == ("answer", None)
    assert message.channel.events == ["typing:start", "typing:stop"]


async def test_slow_turn_posts_a_silent_placeholder_and_keeps_typing() -> None:
    message = _FakeMessage()
    result, placeholder = await think(message, _answer(0.05), after=0.01)  # type: ignore[arg-type]
    assert result == "answer"
    assert placeholder is not None
    # Typing runs the whole turn; the placeholder lands mid-turn and typing is re-triggered
    # straight after it (sending a message clears the sender's typing indicator).
    assert message.channel.events == [
        "typing:start",
        f"reply:{THINKING}",
        "typing:trigger",
        "typing:stop",
    ]
    assert message.reply_kwargs == {"mention_author": False, "silent": True}
    await clear(placeholder)
    assert message.channel.events[-1] == "placeholder:delete"


async def test_placeholder_failure_never_sinks_the_turn() -> None:
    message = _FakeMessage(reply_fails=True)
    result, placeholder = await think(message, _answer(0.05), after=0.01)  # type: ignore[arg-type]
    assert (result, placeholder) == ("answer", None)


async def test_a_failed_turn_retires_its_placeholder() -> None:
    async def boom() -> str:
        await asyncio.sleep(0.05)
        raise RuntimeError("kaboom")

    message = _FakeMessage()
    with pytest.raises(RuntimeError):
        await think(message, boom(), after=0.01)  # type: ignore[arg-type]
    assert message.channel.events[-1] == "placeholder:delete"


async def test_clear_without_a_placeholder_is_a_no_op() -> None:
    await clear(None)
