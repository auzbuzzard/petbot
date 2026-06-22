"""AWS Lambda handler for the core service (the ``transport=lambda`` target).

The frontend invokes this Lambda with a dispatch JSON payload (boto3 ``invoke``); the
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
from typing import Any

from petbot.domain import Process
from petbot.platform import serve
from petbot.services.core import build_process

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

    The event is the ``{"input", "context"}`` dispatch payload from the frontend's boto3
    ``invoke`` (an API Gateway-style ``{"body": ...}`` wrapper is also accepted). The
    return value becomes the invoke response ``Payload`` verbatim — the ``SkillResult``
    itself, which the frontend parses directly.
    """
    body = event["body"] if isinstance(event, dict) and "body" in event else json.dumps(event)
    out = _get_loop().run_until_complete(serve(_get_process(), body))
    result: dict[str, Any] = json.loads(out)
    return result
