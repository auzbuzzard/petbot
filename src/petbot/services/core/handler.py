"""The frontend invokes this Lambda with a dispatch JSON payload (boto3 ``invoke``); the
handler runs it through the service's :class:`~petbot.domain.process.Process` and returns
the :class:`~petbot.domain.result.SkillResult` as the response payload — verbatim, no HTTP
envelope, because the frontend's ``LambdaTransport`` reads the raw invoke ``Payload``
straight into ``SkillResult.model_validate_json``. The process and its event loop are
built once per cold start and reused across invocations — the loop must persist so skills'
async clients (the booru ``httpx.AsyncClient``) stay bound to a live loop.
"""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import nullcontext
from typing import Any

from petbot.domain import Process
from petbot.logging_setup import configure_logging
from petbot.observability import (
    ObservabilitySettings,
    configure_observability,
    flush_observability,
)
from petbot.platform import budget, serve
from petbot.platform.secrets import load_ssm_secrets
from petbot.services.core import RESERVE_SECONDS, build_process

# Cold start, once per execution environment. The Lambda always targets CloudWatch, so
# structured JSON; the dev HTTP entrypoint stays plain.
# The secrets are read from SSM next, before any settings (telemetry's included) are read;
# then the telemetry providers are installed, before build_process reads them.
configure_logging(os.environ.get("LOG_LEVEL", "INFO"), "json")
load_ssm_secrets()
configure_observability(ObservabilitySettings())

_process: Process | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _get_process() -> Process:
    global _process
    if _process is None:
        _process = build_process()
    return _process


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
    return _loop


def handler(event: dict[str, Any], context: object = None) -> dict[str, Any]:
    """Lambda entrypoint: run the dispatched call, return the bare ``SkillResult``.

    The return value becomes the invoke response ``Payload`` verbatim — the ``SkillResult``
    itself, which the frontend parses directly.
    """
    body = event["body"] if isinstance(event, dict) and "body" in event else json.dumps(event)
    # The invocation's own clock sets the turn's budget; a call without a Lambda context
    # (a local test) runs unbounded. An invocation that starts inside the reserve gets a
    # zero budget: the turn answers with its fallback at once rather than being killed.
    remaining_ms = getattr(context, "get_remaining_time_in_millis", None)
    scope = (
        budget(max(0.0, remaining_ms() / 1000 - RESERVE_SECONDS))
        if callable(remaining_ms)
        else nullcontext()
    )
    try:
        with scope:
            out = _get_loop().run_until_complete(serve(_get_process(), body))
        result: dict[str, Any] = json.loads(out)
        return result
    finally:
        # Flush before the runtime freezes — the BatchSpanProcessor would otherwise lose
        # this invocation's spans/metrics until (or unless) the next invoke resumes.
        flush_observability()
