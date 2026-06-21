"""The shared command pipeline, exercised with zero frontend — no Discord, no LLM.

This is the payoff of the ports design: ``dispatch_command`` and ``command_handler``
are testable with a fake ``Skills`` and fake ports, the same code both frontends ride.
"""

from __future__ import annotations

import pytest

from petbot.domain import Platform, SkillContext, SkillResult, User
from petbot.types import COMMANDS, command_handler, dispatch_command
from petbot.types.args import BooruArgs


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:1",
    )


class FakeSkills:
    """Records sibling calls and returns canned results (structural Skills fake)."""

    def __init__(self, results: dict[str, SkillResult]) -> None:
        self._results = results
        self.called: list[str] = []
        self.args: list[object] = []

    def _record(self, name: str):  # type: ignore[no-untyped-def]
        async def call(args: object, ctx: SkillContext) -> SkillResult:
            self.called.append(name)
            self.args.append(args)
            return self._results[name]

        return call

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        return self._record(name)


async def test_dispatch_command_validates_then_dispatches() -> None:
    spec = next(s for s in COMMANDS if s.name == "e621")
    skills = FakeSkills({"e621": SkillResult.message("ok")})
    result = await dispatch_command(spec, skills, _ctx(), tags="fox")
    assert skills.called == ["e621"]
    assert isinstance(skills.args[0], BooruArgs)
    assert skills.args[0].tags == "fox"
    assert result.text == "ok"


async def test_command_handler_extract_dispatch_present() -> None:
    spec = next(s for s in COMMANDS if s.name == "math")
    skills = FakeSkills({"math": SkillResult.message("42")})
    presented: list[SkillResult] = []

    async def present(event: object, result: SkillResult) -> str:
        presented.append(result)
        return result.text or ""

    handle = command_handler(
        spec,
        extract=lambda _event: (skills, _ctx()),
        present=present,
    )
    out = await handle(object(), expression="6*7")
    assert skills.called == ["math"]
    assert presented[0].text == "42"
    assert out == "42"


class _RaisingSkills:
    """Every dispatch fails — stands in for an unreachable worker."""

    def __getattr__(self, name: str):  # type: ignore[no-untyped-def]
        async def call(args: object, ctx: SkillContext) -> SkillResult:
            raise RuntimeError("worker unreachable")

        return call


async def test_command_handler_on_error_maps_and_presents_once() -> None:
    spec = next(s for s in COMMANDS if s.name == "math")
    presented: list[SkillResult] = []

    async def present(event: object, result: SkillResult) -> None:
        presented.append(result)

    handle = command_handler(
        spec,
        extract=lambda _event: (_RaisingSkills(), _ctx()),
        present=present,
        on_error=lambda _event: SkillResult.failure("friendly"),
    )
    await handle(object(), expression="6*7")
    assert len(presented) == 1  # present runs once, on the friendly result
    assert presented[0].error == "friendly"


async def test_command_handler_without_on_error_reraises() -> None:
    spec = next(s for s in COMMANDS if s.name == "math")

    async def present(event: object, result: SkillResult) -> None: ...

    handle = command_handler(
        spec,
        extract=lambda _event: (_RaisingSkills(), _ctx()),
        present=present,
    )
    with pytest.raises(RuntimeError):
        await handle(object(), expression="6*7")
