"""AWS Lambda handler for the core worker (the ``transport=lambda`` target).

The edge invokes this Lambda with a dispatched-call JSON payload (boto3
``invoke``); the handler runs it and returns the
:class:`~petbot.domain.result.SkillResult` as the response payload — verbatim,
no HTTP envelope, because the edge's ``LambdaTransport`` reads the raw invoke
``Payload`` straight into ``SkillResult.model_validate_json``. The worker and its
event loop are built once per cold start and reused across invocations — the loop
must persist so skills' async clients (the booru ``httpx.AsyncClient``) stay bound
to a live loop, exactly as the dev server does.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from petbot.platform import Worker
from petbot.workers.core.worker import build_worker

_worker: Worker | None = None
_loop: asyncio.AbstractEventLoop | None = None


def _get_worker() -> Worker:
    global _worker
    if _worker is None:
        _worker = build_worker()
    return _worker


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None:
        _loop = asyncio.new_event_loop()
    return _loop


def handler(event: dict[str, Any], context: object = None) -> dict[str, Any]:
    """Lambda entrypoint: run the dispatched call, return the bare ``SkillResult``.

    The event is the ``{"skill", "args", "context"}`` dispatch payload from the
    edge's boto3 ``invoke`` (an API Gateway-style ``{"body": ...}`` wrapper is also
    accepted). The return value becomes the invoke response ``Payload`` verbatim,
    so it is the ``SkillResult`` itself — the edge parses it directly.
    """
    body = event["body"] if isinstance(event, dict) and "body" in event else json.dumps(event)
    out = _get_loop().run_until_complete(_get_worker().serve(body))
    result: dict[str, Any] = json.loads(out)
    return result
