"""The worker's transport-agnostic request entry: bytes in, bytes out.

A deploy binding (a Lambda Function URL handler) does almost nothing: read the
request body, call :func:`serve`, return the bytes. All the JSON is the domain
models' own (``model_validate_json`` / ``model_dump_json``).
"""

from __future__ import annotations

from petbot_domain import DispatchRequest
from petbot_platform.worker import Worker


async def serve(worker: Worker, request_json: str | bytes) -> str:
    """Validate a dispatched request, run it, and return the result as JSON."""
    request = DispatchRequest.model_validate_json(request_json)
    result = await worker.handle(request)
    return result.model_dump_json()
