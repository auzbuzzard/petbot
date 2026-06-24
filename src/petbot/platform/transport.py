"""Transports: the way a :class:`~petbot.platform.dispatch.Dispatch` reaches a process.

Two interchangeable implementations of the ``Transport`` port:

* :class:`HttpTransport` — POST the dispatch as JSON to a process HTTP endpoint.
* :class:`LambdaTransport` — invoke a process Lambda synchronously (off-loop, since
  ``boto3`` is blocking). ``boto3`` is an optional extra, imported lazily.

Both encode the dispatch as ``{"input", "context"}`` and read back a
:class:`~petbot.domain.result.SkillResult`. There is no in-process transport: a
co-located process is called directly (the chat process calls its tools through the
:class:`~petbot.platform.registry.ToolRegistry`, not over a transport).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Protocol

import httpx
from opentelemetry.propagate import inject

from petbot.domain import SkillResult
from petbot.platform.dispatch import Dispatch, Transport


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
    """Dispatches by synchronously invoking a process Lambda (off-loop)."""

    def __init__(self, function_name: str, client: _LambdaClient) -> None:
        self._function_name = function_name
        self._client = client

    @classmethod
    def from_function_name(cls, function_name: str) -> LambdaTransport:
        """Build a transport with a default ``boto3`` Lambda client (lazy import)."""
        import boto3

        return cls(function_name, boto3.client("lambda"))

    async def send(self, dispatch: Dispatch) -> SkillResult:
        response = await asyncio.to_thread(
            self._client.invoke,
            FunctionName=self._function_name,
            Payload=json.dumps(_wire(dispatch)).encode(),
        )
        payload: bytes = response["Payload"].read()
        return SkillResult.model_validate_json(payload)
