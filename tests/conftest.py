"""Shared test helpers: fixture loading and a fake aiohttp session.

External booru APIs are never hit live — providers receive a :class:`FakeSession`
that replays a saved JSON fixture, keeping the NSFW-content APIs out of CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import TracebackType
from typing import Any

import aiohttp
import pytest

from petbot.core.skills.context import Capabilities, Platform, SkillContext, User
from petbot.core.skills.ports import VoicePort

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="Run live tests that hit the real booru APIs (needs network allowlist).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: hits real external APIs; off by default. Enable with --run-live or PETBOT_LIVE=1.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Live tests stay opt-in so CI remains fully offline and secret-free.
    if config.getoption("--run-live") or os.environ.get("PETBOT_LIVE"):
        return
    skip_live = pytest.mark.skip(reason="live test: pass --run-live or set PETBOT_LIVE=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


def make_context(
    *,
    allows_explicit: bool = False,
    supports_voice: bool = False,
    voice: VoicePort | None = None,
    display_name: str = "Tester",
    user_id: str = "42",
    conversation_id: str = "conv-1",
) -> SkillContext:
    """Construct a :class:`SkillContext` for tests without a live frontend."""
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id=user_id, display_name=display_name),
        conversation_id=conversation_id,
        capabilities=Capabilities(allows_explicit=allows_explicit, supports_voice=supports_voice),
        voice=voice,
    )


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture by file name (without the .json suffix is also OK)."""
    filename = name if name.endswith(".json") else f"{name}.json"
    data: dict[str, Any] = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return data


class _FakeResponse:
    def __init__(self, payload: Any, status: int) -> None:
        self._payload = payload
        self.status = status

    async def __aenter__(self) -> _FakeResponse:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=None,  # type: ignore[arg-type]
                history=(),
                status=self.status,
            )

    async def json(self, content_type: str | None = None) -> Any:
        return self._payload


class FakeSession:
    """A stand-in for :class:`aiohttp.ClientSession` that replays one payload.

    Records each ``get`` call so tests can assert on URL, params, headers, auth.
    """

    def __init__(self, payload: Any, *, status: int = 200) -> None:
        self.payload = payload
        self.status = status
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: Any = None,
        headers: Any = None,
        auth: Any = None,
    ) -> _FakeResponse:
        self.calls.append({"url": url, "params": params, "headers": headers, "auth": auth})
        return _FakeResponse(self.payload, self.status)


@pytest.fixture
def make_session() -> Any:
    """Return a factory that builds a :class:`FakeSession` from a fixture name."""

    def _factory(fixture_name: str, *, status: int = 200) -> FakeSession:
        return FakeSession(load_fixture(fixture_name), status=status)

    return _factory
