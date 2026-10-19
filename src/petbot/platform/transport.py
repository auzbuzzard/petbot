"""Transports: the way a :class:`~petbot.platform.dispatch.Dispatch` reaches a process.

Two interchangeable implementations of the ``Transport`` port:

* :class:`HttpTransport` — POST the dispatch as JSON to a process HTTP endpoint.
* :class:`LambdaTransport` — invoke a process Lambda synchronously (off-loop, since
  ``boto3`` is blocking). ``boto3`` is an optional extra, imported lazily. It waits out
  a function that isn't ``Active`` yet (see :class:`LambdaTransport`).

Both encode the dispatch as ``{"input", "context"}`` and read back a
:class:`~petbot.domain.result.SkillResult`. There is no in-process transport: a
co-located process is called directly (the chat process calls its tools through the
:class:`~petbot.platform.registry.ToolRegistry`, not over a transport).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Protocol

import httpx
from opentelemetry.propagate import inject

from petbot.domain import SkillResult
from petbot.platform.dispatch import Dispatch, Transport

logger = logging.getLogger(__name__)

#: Invoke error codes meaning "the function exists but isn't ``Active`` yet" — the request
#: never ran, so re-invoking is safe. A container-image function idle for ~2 weeks goes
#: ``Inactive``; the next invoke is *rejected* and starts re-pulling the image (``Pending``,
#: ~20 s), and a deploy leaves it ``Pending`` briefly too.
_NOT_READY = frozenset({"ResourceConflictException", "ResourceNotReadyException"})


def _wire(dispatch: Dispatch) -> dict[str, Any]:
    # Carry the active trace context (W3C tracecontext) alongside the payload so the
    # compute side can re-parent its spans into the same trace. Empty when no SDK is
    # configured; `serve` tolerates a missing/empty "trace" key.
    carrier: dict[str, str] = {}
    inject(carrier)
    return {
        "input": dispatch.input.model_dump(mode="json"),
        "context": dispatch.context.model_dump(mode="json"),
        "trace": carrier,
    }


class HttpTransport(Transport):
    """Dispatches by POSTing the dispatch JSON to a process HTTP endpoint."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        self._url = url
        self._client = client

    async def send(self, dispatch: Dispatch) -> SkillResult:
        response = await self._client.post(self._url, json=_wire(dispatch))
        response.raise_for_status()
        return SkillResult.model_validate_json(response.content)


class _LambdaClient(Protocol):
    """The slice of a boto3 Lambda client this transport uses."""

    def invoke(self, **kwargs: Any) -> Any: ...


class LambdaTransport(Transport):
    """Dispatches by synchronously invoking a process Lambda (off-loop).

    A function that isn't ``Active`` rejects the invoke without running it (see
    :data:`_NOT_READY`), so the invoke is retried with backoff for up to ``ready_timeout``
    seconds instead of failing the first message after an idle spell. A ``FunctionError``
    response (the handler crashed, timed out, or ran out of memory) is raised with the
    runtime's own error payload rather than mis-parsed as a ``SkillResult``.
    """

    def __init__(
        self,
        function_name: str,
        client: _LambdaClient,
        *,
        ready_timeout: float = 60.0,
        retry_delay: float = 1.0,
    ) -> None:
        self._function_name = function_name
        self._client = client
        self._ready_timeout = ready_timeout
        self._retry_delay = retry_delay

    @classmethod
    def from_function_name(cls, function_name: str) -> LambdaTransport:
        """Build a transport with a default ``boto3`` Lambda client (lazy import)."""
        import boto3

        return cls(function_name, boto3.client("lambda"))

    async def send(self, dispatch: Dispatch) -> SkillResult:
        response = await self._invoke(json.dumps(_wire(dispatch)).encode())
        payload: bytes = response["Payload"].read()
        if response.get("FunctionError"):
            raise RuntimeError(
                f"{self._function_name} failed ({response['FunctionError']}): {payload[:500]!r}"
            )
        return SkillResult.model_validate_json(payload)

    async def _invoke(self, payload: bytes) -> Any:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._ready_timeout
        delay = self._retry_delay
        while True:
            try:
                return await asyncio.to_thread(
                    self._client.invoke, FunctionName=self._function_name, Payload=payload
                )
            except Exception as exc:
                code = _error_code(exc)
                if code not in _NOT_READY or loop.time() + delay > deadline:
                    raise
                logger.warning(
                    "%s not ready (%s); retrying in %.0fs", self._function_name, code, delay
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 8.0)


def _error_code(exc: Exception) -> str | None:
    """The AWS error code of a botocore ``ClientError`` (read structurally, so botocore stays
    a lazy import), or ``None`` for anything else."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    code = response.get("Error", {}).get("Code")
    return code if isinstance(code, str) else None
