from __future__ import annotations

import asyncio

from petbot.platform import budget, remaining


def test_no_budget_means_none() -> None:
    assert remaining() is None


def test_budget_counts_down_and_is_scoped() -> None:
    with budget(10):
        left = remaining()
        assert left is not None and 9 < left <= 10
    assert remaining() is None


def test_budget_never_goes_negative() -> None:
    with budget(-5):
        assert remaining() == 0.0


async def test_a_task_created_inside_the_budget_keeps_it() -> None:
    with budget(30):
        task = asyncio.ensure_future(asyncio.sleep(0, result=None))
        seen = asyncio.ensure_future(_remaining_later())
    await task
    left = await seen
    assert left is not None and left > 29


async def _remaining_later() -> float | None:
    await asyncio.sleep(0)
    return remaining()
