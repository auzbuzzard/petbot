"""A plain object satisfies the structural ports, and dispatch round-trips."""

from __future__ import annotations

from petbot_domain import (
    DispatchPort,
    DispatchRequest,
    Platform,
    SkillContext,
    SkillResult,
    User,
)


class _FakeDispatch:
    """Records the request and returns a canned result — no SDK, no network."""

    def __init__(self, result: SkillResult) -> None:
        self.result = result
        self.seen: DispatchRequest | None = None

    async def dispatch(self, request: DispatchRequest) -> SkillResult:
        self.seen = request
        return self.result


def _ctx() -> SkillContext:
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
        conversation_id="discord:42",
    )


def test_fake_dispatch_satisfies_port() -> None:
    assert isinstance(_FakeDispatch(SkillResult.message()), DispatchPort)


async def test_dispatch_forwards_request_and_returns_result() -> None:
    fake = _FakeDispatch(SkillResult.message("done"))
    ctx = _ctx()
    request = DispatchRequest(skill="demo", args={"q": "pony"}, context=ctx)

    out = await fake.dispatch(request)

    assert out.text == "done"
    assert fake.seen is not None
    assert fake.seen.skill == "demo"
    assert fake.seen.args == {"q": "pony"}
    assert fake.seen.context is ctx
