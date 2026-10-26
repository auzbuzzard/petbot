"""The message entrypoint (DM, @mention, reply) end to end: trigger, recall, dispatch,
type while working, render — against fakes, without a gateway."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from petbot.domain import Input, Process, Recalled, SkillContext, SkillResult, TextInput
from petbot.frontends.discord.bot import PetBot
from petbot.frontends.discord.settings import DiscordSettings, HttpService

_BOT_ID = 1


class _User:
    def __init__(self, user_id: int, name: str, *, bot: bool = False) -> None:
        self.id = user_id
        self.display_name = name
        self.bot = bot


class _Channel:
    def __init__(self) -> None:
        self.id = 99
        self.events: list[str] = []

    async def typing(self) -> None:
        self.events.append("typing")

    async def send(self, content: str | None = None, **kwargs: Any) -> None:
        self.events.append(f"send:{content}")


class _Message:
    def __init__(self) -> None:
        self.id = 4242
        self.author = _User(2, "Alice")
        self.content = f"<@{_BOT_ID}> hi"
        self.mentions = [_User(_BOT_ID, "PetBot", bot=True)]
        self.guild = object()
        self.reference = None
        self.channel = _Channel()


class _SlowProcess(Process):
    def __init__(self, delay: float) -> None:
        self._delay = delay
        self.inputs: list[Input] = []

    async def respond(self, inp: Input, ctx: SkillContext) -> SkillResult:
        self.inputs.append(inp)
        await asyncio.sleep(self._delay)
        return SkillResult.message("the answer")


def _bot(process: Process, *, thinking_after: float) -> PetBot:
    settings = DiscordSettings(
        discord_token="x",
        service=HttpService(url="http://svc/dispatch"),
        thinking_after_seconds=thinking_after,
    )
    bot = PetBot(settings)
    bot.process = process
    bot._connection.user = _User(_BOT_ID, "PetBot", bot=True)  # type: ignore[assignment]
    return bot


async def test_quick_mention_answers_without_a_placeholder() -> None:
    process = _SlowProcess(0)
    message = _Message()
    await _bot(process, thinking_after=1).on_message(message)  # type: ignore[arg-type]
    assert message.channel.events == ["typing", "send:the answer"]
    assert process.inputs == [TextInput(text="hi", history=Recalled())]


async def test_slow_mention_only_types_then_answers() -> None:
    message = _Message()
    await _bot(_SlowProcess(0.05), thinking_after=0.01).on_message(message)  # type: ignore[arg-type]
    assert [e for e in message.channel.events if e != "typing"] == ["send:the answer"]
    assert message.channel.events[0] == "typing"


@pytest.mark.parametrize("value", [0, -1])
def test_thinking_threshold_must_be_positive(value: float) -> None:
    with pytest.raises(ValueError):
        DiscordSettings(
            discord_token="x",
            service=HttpService(url="http://svc/dispatch"),
            thinking_after_seconds=value,
        )


class _AtomicClaims:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.claimed: list[str] = []
        self._error = error

    async def claim(self, event_id: str) -> bool:
        if self._error is not None:
            raise self._error
        await asyncio.sleep(0)  # let the other copy's claim interleave
        if event_id in self.claimed:
            return False
        self.claimed.append(event_id)
        return True


async def test_two_copies_on_the_gateway_answer_a_message_once() -> None:
    # A deployment rolling over: old and new edge both receive the same message at once.
    claims = _AtomicClaims()
    process = _SlowProcess(0.01)
    old, new = _bot(process, thinking_after=1), _bot(process, thinking_after=1)
    old.claims = new.claims = claims
    seen_by_old, seen_by_new = _Message(), _Message()
    await asyncio.gather(
        old.on_message(seen_by_old),  # type: ignore[arg-type]
        new.on_message(seen_by_new),  # type: ignore[arg-type]
    )
    assert claims.claimed == ["discord:message:4242"]
    assert len(process.inputs) == 1
    events = [seen_by_old.channel.events, seen_by_new.channel.events]
    assert sorted(events) == [[], ["typing", "send:the answer"]]


async def test_a_failing_claim_store_still_answers() -> None:
    process = _SlowProcess(0)
    bot = _bot(process, thinking_after=1)
    bot.claims = _AtomicClaims(error=OSError("dynamodb down"))
    message = _Message()
    await bot.on_message(message)  # type: ignore[arg-type]
    assert message.channel.events == ["typing", "send:the answer"]
