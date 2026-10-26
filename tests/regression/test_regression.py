"""Every golden case against the deployed core, ``trials`` times; a case passes only when
every trial does (pass^k)."""

from __future__ import annotations

import logging

import pytest

from petbot.platform import ProcessClient

from .golden import Case, CaseReport, Trial, grade, load_cases

logger = logging.getLogger(__name__)

CASES = load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
async def test_case_passes_every_trial(
    core: ProcessClient, reports: list[CaseReport], trials: int, case: Case
) -> None:
    ran: list[Trial] = []
    for _ in range(trials):
        try:
            result = await core.respond(case.input(), case.context())
        except Exception as exc:
            # The exception's text goes to the log only, never to the summary.
            logger.exception("dispatch failed")
            ran.append(Trial(None, (f"the dispatch failed ({type(exc).__name__})",)))
        else:
            ran.append(Trial(result, tuple(grade(case, result))))
    reports.append(CaseReport(case, tuple(ran)))
    failed = {n: t.problems for n, t in enumerate(ran, 1) if not t.passed}
    assert not failed, f"{case.id}: {len(failed)} of {trials} trials failed: {failed}"
