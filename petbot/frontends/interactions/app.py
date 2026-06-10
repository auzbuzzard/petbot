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

from petbot.config import ConfigError, Settings
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


def build_handler(settings: Settings, *, http_client: httpx.AsyncClient) -> InteractionHandler:
    """Wire the stateless skills into an :class:`InteractionHandler`.

    Raises :class:`ConfigError` if ``DISCORD_PUBLIC_KEY`` is unset — it is
    required to verify Discord's request signatures.
    """
    if not settings.discord_public_key:
        raise ConfigError(
            "DISCORD_PUBLIC_KEY is not set. The HTTP-Interactions frontend needs the "
            "application's public key (Discord Developer Portal, General Information) "
            "to verify request signatures."
        )
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


#: Set once per warm container so :func:`configure_logging` (which restarts the
#: queue listener on each call) runs a single time, not per invocation.
_logging_configured = False


def _ensure_logging_configured(settings: Settings) -> None:
    """Configure process logging once per container (never at import time).

    Mirrors the gateway, which configures logging in ``bootstrap.run``; the
    Lambda entrypoint is the equivalent start-up point here, so the interactions
    frontend emits the same structured/plain logs (see ADR 0004) instead of the
    root logger's unconfigured default.
    """
    global _logging_configured
    if not _logging_configured:
        configure_logging(level=settings.log_level, fmt=settings.resolved_log_format)
        _logging_configured = True


async def _ahandle(event: Mapping[str, Any], settings: Settings) -> tuple[int, dict[str, Any]]:
    # A short-lived client per invocation keeps it bound to this event loop. A
    # warm-reuse optimization can come later if traffic warrants it.
    async with httpx.AsyncClient(timeout=20.0) as client:
        handler = build_handler(settings, http_client=client)
        body, signature, timestamp = _extract(event)
        return await handler.handle(body, signature=signature, timestamp=timestamp)


def lambda_handler(event: Mapping[str, Any], context: Any = None) -> dict[str, Any]:
    """AWS Lambda Function URL handler: parse the event, run, return a response."""
    settings = Settings.from_env()
    _ensure_logging_configured(settings)
    status, payload = asyncio.run(_ahandle(event, settings))
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }
