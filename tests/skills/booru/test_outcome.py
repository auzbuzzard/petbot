"""The booru outcome signal: a coarse, non-content status tagged on the active tool span,
recorded without the tags or the result."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

import httpx
import respx
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from conftest import load_fixture, make_context
from petbot.domain import EmptyResult, UpstreamUnavailable
from petbot.skills.booru.skill import E621Skill
from petbot.types import BooruArgs


async def _outcome_of(run: Callable[[], Awaitable[object]]) -> object:
    """Run ``run`` inside a tool span and return the ``petbot.booru.outcome`` it tagged.
    Expected booru failures are swallowed — we only care about the recorded status."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    with provider.get_tracer("tool").start_as_current_span("execute_tool e621"):
        try:
            await run()
        except (EmptyResult, UpstreamUnavailable):
            pass
    span = exporter.get_finished_spans()[0]
    return (span.attributes or {}).get("petbot.booru.outcome")


def _skill(client: httpx.AsyncClient) -> E621Skill:
    return E621Skill(client=client, user_agent="PetBot/2.1 (test)")


@respx.mock
async def test_outcome_ok() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_success"))
    )
    async with httpx.AsyncClient() as client:
        outcome = await _outcome_of(
            lambda: _skill(client).run(BooruArgs(tags="canine"), make_context(allows_explicit=True))
        )
    assert outcome == "ok"


@respx.mock
async def test_outcome_safe_limited_when_safe_floor_empties_it() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_empty"))
    )
    async with httpx.AsyncClient() as client:
        outcome = await _outcome_of(
            lambda: _skill(client).run(
                BooruArgs(tags="canine"), make_context(allows_explicit=False)
            )
        )
    assert outcome == "safe_limited"


@respx.mock
async def test_outcome_empty_when_nsfw_search_finds_nothing() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(200, json=load_fixture("e621_empty"))
    )
    async with httpx.AsyncClient() as client:
        outcome = await _outcome_of(
            lambda: _skill(client).run(BooruArgs(tags="canine"), make_context(allows_explicit=True))
        )
    assert outcome == "empty"


@respx.mock
async def test_outcome_error_on_site_failure() -> None:
    respx.get("https://e621.net/posts.json").mock(
        return_value=httpx.Response(422, json=load_fixture("e621_error"))
    )
    async with httpx.AsyncClient() as client:
        outcome = await _outcome_of(
            lambda: _skill(client).run(BooruArgs(tags="x"), make_context(allows_explicit=True))
        )
    assert outcome == "error"
