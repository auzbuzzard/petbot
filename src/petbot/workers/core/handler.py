"""AWS Lambda handler for the core worker (the ``transport=lambda`` target).

The edge invokes this Lambda with a dispatched-call JSON payload; the handler runs
it and returns the :class:`~petbot.domain.result.SkillResult` JSON. The worker and
its event loop are built once per cold start and reused across invocations — the
loop must persist so skills' async clients (the booru ``httpx.AsyncClient``) stay
bound to a live loop, exactly as the dev server does.
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
    """Lambda entrypoint: run the dispatched call, return its result as JSON.

    Accepts either a direct ``SkillCall`` payload (``boto3`` ``invoke``) or an API
    Gateway-style event with a ``body`` string.
    """
    body = event["body"] if isinstance(event, dict) and "body" in event else json.dumps(event)
    out = _get_loop().run_until_complete(_get_worker().serve(body))
    return {"statusCode": 200, "headers": {"content-type": "application/json"}, "body": out}
