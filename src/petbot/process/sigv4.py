"""SigV4 request signing for an OpenAI-compatible AWS endpoint (Bedrock's ``bedrock-mantle``).

:class:`SigV4Auth` is an ``httpx.Auth`` that signs each request with the runtime's own AWS
credentials (the Lambda role, or the developer's profile locally), so the chat model needs
no API key. The OpenAI client still sends its placeholder ``Authorization: Bearer`` header;
signing replaces it. ``botocore`` is imported lazily: only this provider pulls it in.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any
from urllib.parse import urlparse

import httpx

#: The SigV4 signing name of Bedrock's OpenAI-compatible endpoint (and its IAM prefix).
MANTLE_SERVICE = "bedrock-mantle"


def mantle_region(base_url: str) -> str:
    """The Region of a ``https://bedrock-mantle.<region>.api.aws/...`` base URL, which is the
    Region its requests are signed for."""
    host = urlparse(base_url).hostname or ""
    service, _, rest = host.partition(".")
    region, _, domain = rest.partition(".")
    if service != MANTLE_SERVICE or not region or domain != "api.aws":
        raise ValueError(f"not a bedrock-mantle endpoint: {base_url!r}")
    return region


class SigV4Auth(httpx.Auth):
    """Signs every request for ``service`` in ``region`` (AWS Signature Version 4).

    Only ``Content-Type`` and ``Host`` are signed besides AWS's own headers, so a header the
    transport adds or rewrites after signing (``Content-Length``, ``User-Agent``) can't
    invalidate the signature. The credentials are resolved on each request, so a
    refreshable session (an assumed role, SSO) stays current; resolving may refresh them
    over the network, so the async flow signs off the event loop.
    """

    requires_request_body = True

    def __init__(self, service: str, region: str, credentials: Any = None) -> None:
        from botocore.session import Session

        self._service = service
        self._region = region
        self._credentials = credentials or Session().get_credentials()
        if self._credentials is None:
            raise ValueError(f"no AWS credentials to sign {service} requests with")

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        self._sign(request)
        yield request

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        await request.aread()
        await asyncio.to_thread(self._sign, request)
        yield request

    def _sign(self, request: httpx.Request) -> None:
        from botocore.auth import SigV4Auth as BotocoreSigV4
        from botocore.awsrequest import AWSRequest

        signed = AWSRequest(method=request.method, url=str(request.url), data=request.content)
        if content_type := request.headers.get("Content-Type"):
            signed.headers["Content-Type"] = content_type
        frozen = self._credentials.get_frozen_credentials()
        BotocoreSigV4(frozen, self._service, self._region).add_auth(signed)
        request.headers.pop("Authorization", None)
        request.headers.update(dict(signed.headers.items()))
