"""Composition root and AWS Lambda Function URL entrypoint.

:func:`build_handler` wires the stateless skills into an
:class:`InteractionHandler`; :func:`lambda_handler` is the AWS Lambda Function
URL binding. The Terraform stack (#30) points the function at
``petbot.frontends.interactions.app.lambda_handler``.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from typing import Any

import httpx

from petbot.config import InteractionsSettings
from petbot.core.skills.booru_skill import DerpiSkill, E621Skill
from petbot.core.skills.context import Capabilities
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.registry import SkillRegistry
from petbot.frontends.interactions.handler import InteractionHandler
from petbot.logging_setup import configure_logging

#: Capabilities of the stateless HTTP-interactions frontend: no voice (so the
#: registry hides ``/music``), rich embeds, Discord's 2000-char limit.
INTERACTIONS_CAPABILITIES = Capabilities(
    supports_voice=False,
    supports_rich_embeds=True,
    max_text_length=2000,
)


def build_handler(
    settings: InteractionsSettings, *, http_client: httpx.AsyncClient
) -> InteractionHandler:
    """Wire the stateless skills into an :class:`InteractionHandler`.

    ``settings`` guarantees a ``discord_public_key`` (constructing
    :class:`InteractionsSettings` fails otherwise), so the signature-verification
    key is always present here.
    """
    registry = SkillRegistry(
        [
            MathSkill(),
            DerpiSkill(client=http_client, api_key=settings.derpibooru_api_key),
            E621Skill(
                client=http_client,
                user_agent=settings.user_agent,
                username=settings.e621_username,
                api_key=settings.e621_api_key,
            ),
        ]
    )
    return InteractionHandler(
        registry=registry,
        capabilities=INTERACTIONS_CAPABILITIES,
        public_key=settings.discord_public_key,
    )


def _extract(event: Mapping[str, Any]) -> tuple[bytes, str | None, str | None]:
    """Pull the raw body and signature headers out of a Function URL event."""
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    raw = event.get("body") or ""
    body = base64.b64decode(raw) if event.get("isBase64Encoded") else raw.encode()
    return body, headers.get("x-signature-ed25519"), headers.get("x-signature-timestamp")


#: Process-wide settings, built once per warm container on the first invocation
#: (not at import, so the module stays importable for tests/tooling). Caching here
#: keeps env parsing/validation and logging setup off the per-request path; a
#: misconfigured function fails on its first invocation rather than every call.
_settings: InteractionsSettings | None = None


def _startup() -> InteractionsSettings:
    """Build settings and configure logging once per container; reuse thereafter.

    Mirrors the gateway, which configures logging in ``bootstrap.run``; the first
    Lambda invocation is the equivalent start-up point, so the interactions
    frontend emits the same structured/plain logs (ADR 0004).
    """
    global _settings
    if _settings is None:
        settings = InteractionsSettings()
        configure_logging(level=settings.log_level, fmt=settings.resolved_log_format)
        _settings = settings
    return _settings


async def _ahandle(
    event: Mapping[str, Any], settings: InteractionsSettings
) -> tuple[int, dict[str, Any]]:
    # A short-lived client per invocation keeps it bound to this event loop. A
    # warm-reuse optimization can come later if traffic warrants it.
    async with httpx.AsyncClient(timeout=20.0) as client:
        handler = build_handler(settings, http_client=client)
        body, signature, timestamp = _extract(event)
        return await handler.handle(body, signature=signature, timestamp=timestamp)


def lambda_handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda Function URL handler: parse the event, run, return a response."""
    settings = _startup()
    status, payload = asyncio.run(_ahandle(event, settings))
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }
