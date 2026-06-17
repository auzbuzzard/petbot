"""AWS Lambda handler for the brain worker (the prod ``transport=lambda`` target).

The edge invokes this Lambda with a :class:`~petbot.domain.call.SkillCall` JSON
payload; the handler runs it and returns the :class:`~petbot.domain.result.SkillResult`
JSON. The worker is built once per cold start and reused across invocations.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from petbot.platform import Worker
from petbot.workers.brain.worker import build_worker

_worker: Worker | None = None


def _get_worker() -> Worker:
    global _worker
    if _worker is None:
        _worker = build_worker()
    return _worker


def handler(event: dict[str, Any], context: object = None) -> dict[str, Any]:
    """Lambda entrypoint: run the dispatched call, return its result as JSON.

    Accepts either a direct ``SkillCall`` payload (``boto3`` ``invoke``) or an API
    Gateway-style event with a ``body`` string.
    """
    body = event["body"] if isinstance(event, dict) and "body" in event else json.dumps(event)
    out = asyncio.run(_get_worker().serve(body))
    return {"statusCode": 200, "headers": {"content-type": "application/json"}, "body": out}
