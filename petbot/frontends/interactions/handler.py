"""The interaction handler: verify → parse → dispatch → render.

Framework-agnostic on purpose. :meth:`InteractionHandler.handle` takes the raw
request body plus the two signature headers and returns an
``(http_status, response_json)`` pair, so it is exercised by unit tests with no
HTTP server and bound to a concrete runtime (AWS Lambda) in :mod:`.app`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from petbot.core.skills.context import Capabilities, SkillResult
from petbot.core.skills.registry import SkillNotFoundError, SkillRegistry
from petbot.frontends.interactions.context import build_context
from petbot.frontends.interactions.render import message_response
from petbot.frontends.interactions.verify import verify_signature
from petbot.frontends.interactions.wire import APPLICATION_COMMAND, PING, PONG

log = logging.getLogger("petbot.interactions")


class InteractionHandler:
    """Verifies, routes, and renders a single Discord interaction."""

    def __init__(
        self,
        *,
        registry: SkillRegistry,
        capabilities: Capabilities,
        public_key: str,
    ) -> None:
        self._registry = registry
        self._capabilities = capabilities
        self._public_key = public_key
        # The skills this frontend may expose, by name. Capability gating means
        # voice-only skills (``/music``) are absent here automatically.
        self._allowed = {skill.name for skill in registry.available_for(capabilities)}

    async def handle(
        self,
        body: bytes,
        *,
        signature: str | None,
        timestamp: str | None,
    ) -> tuple[int, dict[str, Any]]:
        """Process one interaction; return ``(status, response_json)``.

        Returns 401 on a missing/invalid signature (Discord requires this), 400
        on unparseable JSON, and 200 with an interaction response otherwise.
        """
        if (
            not signature
            or not timestamp
            or not verify_signature(self._public_key, timestamp, body, signature)
        ):
            return 401, {"error": "invalid request signature"}

        try:
            interaction = json.loads(body)
        except json.JSONDecodeError:
            return 400, {"error": "invalid JSON body"}

        itype = interaction.get("type")
        if itype == PING:
            return 200, {"type": PONG}
        if itype == APPLICATION_COMMAND:
            return 200, await self._dispatch(interaction)
        return 200, message_response(SkillResult.failure("Unsupported interaction type."))

    async def _dispatch(self, interaction: Mapping[str, Any]) -> dict[str, Any]:
        data = interaction.get("data") or {}
        name = str(data.get("name", ""))

        # ``/ping`` is an adapter-level liveness check, not a neutral skill
        # (mirrors the gateway adapter's PingCog).
        if name == "ping":
            return message_response(SkillResult.message("🏓 Pong!"))

        if name not in self._allowed:
            # NOTE: ``/purge`` acts on Discord directly (REST bulk-delete +
            # Manage Messages gating) rather than via a neutral skill; it is a
            # tracked follow-up and is intentionally not handled here yet.
            log.warning("Received unhandled command: /%s", name)
            return message_response(SkillResult.failure(f"`/{name}` isn't available here yet."))

        args = {
            option["name"]: option["value"]
            for option in data.get("options", [])
            if isinstance(option, Mapping) and "value" in option
        }
        ctx = build_context(interaction)
        try:
            skill = self._registry.get(name)
        except SkillNotFoundError:
            return message_response(SkillResult.failure(f"Unknown command: `/{name}`."))
        result = await skill.run(args, ctx)
        return message_response(result)
