"""Transports: the one way a :class:`~petbot.domain.call.SkillCall` reaches a worker.

Three interchangeable implementations of the ``Transport`` port:

* :class:`LocalTransport` — same process; runs the call directly with its typed
  args, **no serialisation**.
* :class:`HttpTransport` — POST the call as JSON to a worker HTTP endpoint.
* :class:`LambdaTransport` — invoke a worker Lambda synchronously (off-loop,
  since ``boto3`` is blocking). ``boto3`` is an optional extra, imported lazily.

Serialisation lives only in the two remote transports — the in-process path never
touches JSON. Each encodes the call as ``{"skill", "args", "context"}`` and reads
back a :class:`~petbot.domain.result.SkillResult`.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, Protocol

import httpx

from petbot.domain import SkillCall, SkillResult, Transport

if TYPE_CHECKING:
    from petbot.platform.worker import Worker


def _wire(call: SkillCall) -> dict[str, Any]:
    return {
        "skill": call.skill,
        "args": call.args.model_dump(mode="json"),
        "context": call.context.model_dump(mode="json"),
    }


class LocalTransport(Transport):
    """Runs the call in-process against a :class:`Worker` — no serialisation."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker

    async def send(self, call: SkillCall) -> SkillResult:
        return await self._worker.run(call)


class HttpTransport(Transport):
    """Dispatches a call by POSTing its JSON to a worker HTTP endpoint."""

    def __init__(self, url: str, client: httpx.AsyncClient) -> None:
        self._url = url
        self._client = client

    async def send(self, call: SkillCall) -> SkillResult:
        response = await self._client.post(self._url, json=_wire(call))
        response.raise_for_status()
        return SkillResult.model_validate_json(response.content)


class _LambdaClient(Protocol):
    """The slice of a boto3 Lambda client this transport uses."""

    def invoke(self, **kwargs: Any) -> Any: ...


class LambdaTransport(Transport):
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
            Payload=json.dumps(_wire(call)).encode(),
        )
        payload: bytes = response["Payload"].read()
        return SkillResult.model_validate_json(payload)
