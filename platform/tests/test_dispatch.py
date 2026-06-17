"""HttpDispatch <-> serve: a request round-trips through real HTTP serialisation,
in-memory (no network, no AWS)."""

from __future__ import annotations

from typing import Any

import httpx

from petbot_domain import DispatchPort, DispatchRequest, Platform, SkillContext, User
from petbot_platform import HttpDispatch, Worker, serve


def _request(skill: str, **args: Any) -> DispatchRequest:
    return DispatchRequest(
        skill=skill,
        args=args,
        context=SkillContext(
            platform=Platform.DISCORD,
            user=User(platform=Platform.DISCORD, id="1", display_name="tester"),
            conversation_id="discord:1",
        ),
    )


async def test_satisfies_dispatch_port() -> None:
    async with httpx.AsyncClient() as client:
        assert isinstance(HttpDispatch("http://worker", client=client), DispatchPort)


async def test_round_trips_edge_to_worker() -> None:
    worker = Worker.from_installed_skills()

    async def handler(request: httpx.Request) -> httpx.Response:
        # The worker side: deserialise -> run -> serialise.
        return httpx.Response(200, content=await serve(worker, request.content))

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        dispatch = HttpDispatch("http://worker/dispatch", client=client)
        result = await dispatch.dispatch(_request("math", expression="6 * 7"))

    assert result.text is not None
    assert "42" in result.text
