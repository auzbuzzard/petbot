"""Live tests: run against a deployed core, never in the offline suite.

deploy.yml's ``test`` job runs them after every deploy to dev (each pull request from this
repository), with ``PETBOT_LIVE_FUNCTION=petbot-dev-core``; without it every test here is
skipped. They dispatch as the Discord frontend does (:class:`~petbot.platform.ProcessClient`
over :class:`~petbot.platform.LambdaTransport`) with the job's AWS credentials, so a failure is
something the deployed function does: its model, network, permissions or packaging. Each test
appends what it saw to ``PETBOT_LIVE_TRANSCRIPTS`` (the job's summary), when set.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest

from petbot.domain import Platform, SkillContext, User
from petbot.platform import LambdaTransport, ProcessClient

FUNCTION = os.environ.get("PETBOT_LIVE_FUNCTION", "")
_LIVE_DIR = Path(__file__).parent

#: Appends one exchange (a title and what was said) to the job's transcripts.
Record = Callable[[str, str], None]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if FUNCTION:
        return
    skip = pytest.mark.skip(reason="live: set PETBOT_LIVE_FUNCTION to a deployed core")
    for item in items:
        if _LIVE_DIR in Path(str(item.path)).parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def core() -> ProcessClient:
    """The deployed core, reached as the frontend reaches it."""
    return ProcessClient(LambdaTransport.from_function_name(FUNCTION))


@pytest.fixture
def ctx() -> SkillContext:
    """A message in an ordinary (not age-gated) server channel."""
    return SkillContext(
        platform=Platform.DISCORD,
        user=User(platform=Platform.DISCORD, id="live:tester", display_name="tester"),
        conversation_id="live:tests",
        community_name="Live tests",
        channel_name="general",
    )


@pytest.fixture
def record() -> Record:
    """Appends to the transcripts file the job posts, if it names one."""

    def append(title: str, body: str) -> None:
        path = os.environ.get("PETBOT_LIVE_TRANSCRIPTS")
        if path:
            with open(path, "a", encoding="utf-8") as out:
                out.write(f"#### {title}\n\n```text\n{body.rstrip()}\n```\n\n")

    return append
