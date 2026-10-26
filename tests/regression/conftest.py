"""The regression suite runs against a deployed core, never in the offline suite.

deploy.yml's ``test`` job runs it after every deploy to dev, with
``PETBOT_REGRESSION_FUNCTION=petbot-dev-core``; without it every test that dispatches is
skipped (the grader's own tests still run). Tests dispatch as the Discord frontend does
(:class:`~petbot.platform.ProcessClient` over :class:`~petbot.platform.LambdaTransport`)
with the caller's AWS credentials. ``PETBOT_REGRESSION_TRIALS`` (default 3) sets how often
each case runs, and ``PETBOT_REGRESSION_SUMMARY`` names a file the per-case results are
written to as markdown (the job's summary).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from petbot.platform import LambdaTransport, ProcessClient

from .golden import CaseReport, summary

_DIR = Path(__file__).parent
FUNCTION = os.environ.get("PETBOT_REGRESSION_FUNCTION", "")
TRIALS = int(os.environ.get("PETBOT_REGRESSION_TRIALS", "3"))
if TRIALS < 1:
    raise ValueError("PETBOT_REGRESSION_TRIALS must be at least 1")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if FUNCTION:
        return
    skip = pytest.mark.skip(reason="set PETBOT_REGRESSION_FUNCTION to a deployed core")
    for item in items:
        here = _DIR in Path(str(item.path)).parents
        if here and "core" in getattr(item, "fixturenames", ()):
            item.add_marker(skip)


@pytest.fixture(scope="session")
def core() -> ProcessClient:
    return ProcessClient(LambdaTransport.from_function_name(FUNCTION))


@pytest.fixture(scope="session")
def trials() -> int:
    return TRIALS


@pytest.fixture(scope="session")
def reports() -> Iterator[list[CaseReport]]:
    collected: list[CaseReport] = []
    yield collected
    path = os.environ.get("PETBOT_REGRESSION_SUMMARY")
    if path and collected:
        Path(path).write_text(summary(FUNCTION, TRIALS, collected), encoding="utf-8")
