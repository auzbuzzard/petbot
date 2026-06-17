"""``HttpDispatch`` — the edge's remote ``DispatchPort``.

The one real dispatch implementation: POST the request JSON to the worker's URL
and read the result JSON back. Works against a Lambda Function URL, a container,
or a homelab worker — the edge never knows which. A different transport (e.g.
boto3 ``lambda.invoke``) would be another ``DispatchPort`` behind the same seam.
"""

from __future__ import annotations

import httpx

from petbot_domain import DispatchRequest, SkillResult


class HttpDispatch:
    """A :class:`~petbot_domain.DispatchPort` that calls a worker over HTTP."""

    def __init__(self, worker_url: str, *, client: httpx.AsyncClient) -> None:
        self._url = worker_url
        self._client = client

    async def dispatch(self, request: DispatchRequest) -> SkillResult:
        response = await self._client.post(
            self._url,
            content=request.model_dump_json(),
            headers={"content-type": "application/json"},
        )
        response.raise_for_status()
        return SkillResult.model_validate_json(response.content)
