"""Transports: the one way a :class:`~petbot.domain.call.SkillCall` reaches a worker.

Two interchangeable implementations behind the single ``Transport`` port:

* :class:`HttpTransport` — POST the call JSON to a worker HTTP endpoint. Used in
  dev and for an always-on/container worker.
* :class:`LambdaTransport` — invoke a worker Lambda synchronously. ``boto3`` is
  blocking, so the invoke is offloaded with ``asyncio.to_thread`` to keep the
  edge's event loop free. ``boto3`` is an optional extra, imported lazily.

Both speak pydantic JSON on the wire: ``call.model_dump_json`` out,
``SkillResult.model_validate_json`` back.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

import httpx

from petbot.domain import SkillCall, SkillResult


class HttpTransport:
    """Dispatches a call by POSTing its JSON to a worker HTTP endpoint."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        self._url = url
        self._client = client

    async def send(self, call: SkillCall) -> SkillResult:
        response = await self._client.post(
            self._url,
            content=call.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        response.raise_for_status()
        return SkillResult.model_validate_json(response.content)


class _LambdaClient(Protocol):
    """The slice of a boto3 Lambda client this transport uses."""

    def invoke(self, **kwargs: Any) -> Any: ...


class LambdaTransport:
    """Dispatches a call by synchronously invoking a worker Lambda (off-loop)."""

    def __init__(self, function_name: str, client: _LambdaClient) -> None:
        self._function_name = function_name
        self._client = client

    @classmethod
    def from_function_name(cls, function_name: str) -> LambdaTransport:
        """Build a transport with a default ``boto3`` Lambda client (lazy import)."""
        import boto3

        return cls(function_name, boto3.client("lambda"))

    async def send(self, call: SkillCall) -> SkillResult:
        response = await asyncio.to_thread(
            self._client.invoke,
            FunctionName=self._function_name,
            Payload=call.model_dump_json().encode(),
        )
        payload: bytes = response["Payload"].read()
        return SkillResult.model_validate_json(payload)
