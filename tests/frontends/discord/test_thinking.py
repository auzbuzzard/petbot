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


def _forbidden() -> discord.Forbidden:
    return discord.Forbidden(_FakeResp(), "Missing Permissions")  # type: ignore[arg-type]


class _FakeChannel:
    def __init__(self, *, typing_error: Exception | None = None) -> None:
        self.events: list[str] = []
        self._typing_error = typing_error

    async def typing(self) -> None:
        # `await channel.typing()` is one trigger in discord.py.
        if self._typing_error is not None:
            raise self._typing_error
        self.events.append("typing")


class _FakePlaceholder:
    def __init__(self, channel: _FakeChannel, *, delete_error: Exception | None) -> None:
        self._channel = channel
        self._delete_error = delete_error

    async def delete(self) -> None:
        if self._delete_error is not None:
            raise self._delete_error
        self._channel.events.append("placeholder:delete")


class _FakeMessage:
    def __init__(
        self,
        *,
        reply_error: Exception | None = None,
        delete_error: Exception | None = None,
        typing_error: Exception | None = None,
    ) -> None:
        self.channel = _FakeChannel(typing_error=typing_error)
        self._reply_error = reply_error
        self._delete_error = delete_error
        self.reply_kwargs: dict[str, Any] = {}

    async def reply(self, content: str, **kwargs: Any) -> _FakePlaceholder:
        if self._reply_error is not None:
            raise self._reply_error
        self.channel.events.append(f"reply:{content}")
        self.reply_kwargs = kwargs
        return _FakePlaceholder(self.channel, delete_error=self._delete_error)


async def _answer(delay: float) -> str:
    await asyncio.sleep(delay)
    return "answer"


async def test_quick_turn_only_types() -> None:
    message = _FakeMessage()
    result, placeholder = await think(message, _answer(0.01), after=1)  # type: ignore[arg-type]
    assert (result, placeholder) == ("answer", None)
    assert message.channel.events == ["typing"]


async def test_slow_turn_posts_a_silent_placeholder_and_keeps_typing() -> None:
    message = _FakeMessage()
    result, placeholder = await think(message, _answer(0.05), after=0.01)  # type: ignore[arg-type]
    assert result == "answer"
    assert placeholder is not None
    # Typing from the start; the placeholder lands mid-turn and typing is re-triggered
    # straight after it (sending a message clears the sender's typing indicator).
    assert message.channel.events == ["typing", f"reply:{THINKING}", "typing"]
    assert message.reply_kwargs == {"mention_author": False, "silent": True}
    await clear(placeholder)
    assert message.channel.events[-1] == "placeholder:delete"


@pytest.mark.parametrize("error", [_forbidden(), OSError("connection reset")])
async def test_cosmetic_failures_never_sink_the_turn(error: Exception) -> None:
    # Typing and the placeholder are decoration: a permission error or a network blip on
    # either must still deliver the answer.
    message = _FakeMessage(reply_error=error, typing_error=error, delete_error=error)
    result, placeholder = await think(message, _answer(0.05), after=0.01)  # type: ignore[arg-type]
    assert (result, placeholder) == ("answer", None)

    posted = _FakeMessage(delete_error=error)
    _, placeholder = await think(posted, _answer(0.05), after=0.01)  # type: ignore[arg-type]
    await clear(placeholder)  # the delete fails, and is only logged


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
