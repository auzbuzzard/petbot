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
import math
from typing import Any, Protocol

import httpx
from opentelemetry.propagate import inject

from petbot.domain import SkillResult
from petbot.platform._aws import aws_error_code
from petbot.platform.dispatch import Dispatch, Transport
from petbot.platform.progress import Phase, report

logger = logging.getLogger(__name__)

#: Invoke error codes meaning "the function exists but isn't ``Active`` yet" — the request
#: never ran, so re-invoking is safe.
_NOT_READY = frozenset({"ResourceConflictException", "ResourceNotReadyException"})

_READY_POLL_SECONDS = 2

#: Lambda's maximum function timeout. The SDK's read timeout sits above it so the client
#: never abandons, and so never re-sends, an invocation Lambda is still running.
_LAMBDA_MAX_TIMEOUT_SECONDS = 900


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
    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        self._url = url
        self._client = client

    async def send(self, dispatch: Dispatch) -> SkillResult:
        response = await self._client.post(self._url, json=_wire(dispatch))
        response.raise_for_status()
        return SkillResult.model_validate_json(response.content)


class _LambdaClient(Protocol):
    def invoke(self, **kwargs: Any) -> Any: ...

    def get_waiter(self, waiter_name: str) -> Any: ...


class LambdaTransport(Transport):
    """Dispatches by synchronously invoking a process Lambda (off-loop).

    A function that isn't ``Active`` rejects an invoke without running it (see
    :data:`_NOT_READY`). On that rejection the transport waits, for up to ``ready_timeout``
    seconds, until boto3's ``function_active`` waiter sees the function ``Active``, then
    invokes once more, reporting :attr:`~Phase.WAKING` then :attr:`~Phase.THINKING` to the
    turn's observer (see :mod:`petbot.platform.progress`). A ``FunctionError`` response (the
    handler crashed, timed out, or ran out of memory) is raised with the runtime's own error
    payload; only a clean response is parsed as a ``SkillResult``.
    """

    def __init__(
        self, function_name: str, client: _LambdaClient, *, ready_timeout: float = 120.0
    ) -> None:
        self._function_name = function_name
        self._client = client
        self._ready_timeout = ready_timeout

    @classmethod
    def from_function_name(cls, function_name: str) -> LambdaTransport:
        """Build a transport with a ``boto3`` Lambda client (lazy import) configured so the
        SDK never re-sends an invocation: no SDK retries, and a read timeout above any
        function's timeout. A re-sent invocation would run the whole turn again."""
        import boto3
        from botocore.config import Config

        config = Config(
            read_timeout=_LAMBDA_MAX_TIMEOUT_SECONDS + 10,
            retries={"total_max_attempts": 1},
        )
        return cls(function_name, boto3.client("lambda", config=config))

    async def send(self, dispatch: Dispatch) -> SkillResult:
        response = await self._invoke(json.dumps(_wire(dispatch)).encode())
        payload: bytes = response["Payload"].read()
        if response.get("FunctionError"):
            raise RuntimeError(
                f"{self._function_name} failed ({response['FunctionError']}): {payload[:500]!r}"
            )
        return SkillResult.model_validate_json(payload)

    async def _invoke(self, payload: bytes) -> Any:
        try:
            return await self._call(payload)
        except Exception as exc:
            code = aws_error_code(exc)
            if code not in _NOT_READY:
                raise
            logger.warning(
                "%s not ready (%s); waiting for it to become Active", self._function_name, code
            )
        report(Phase.WAKING)
        await asyncio.to_thread(self._wait_until_active)
        report(Phase.THINKING)
        return await self._call(payload)

    async def _call(self, payload: bytes) -> Any:
        return await asyncio.to_thread(
            self._client.invoke, FunctionName=self._function_name, Payload=payload
        )

    def _wait_until_active(self) -> None:
        # The waiter keeps polling through `Inactive` and `Pending`, succeeds on `Active`,
        # and raises a WaiterError on `Failed` or once `ready_timeout` is spent.
        self._client.get_waiter("function_active").wait(
            FunctionName=self._function_name,
            WaiterConfig={
                "Delay": _READY_POLL_SECONDS,
                "MaxAttempts": max(1, math.ceil(self._ready_timeout / _READY_POLL_SECONDS)),
            },
        )
