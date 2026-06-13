"""Tests for the HTTP-Interactions frontend (offline; no HTTP server, no network).

Signatures are exercised with a real Ed25519 keypair generated per test, so the
verification path is genuinely tested rather than stubbed.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Any, ClassVar

import httpx
import pytest
from nacl.signing import SigningKey

from petbot.config import InteractionsSettings
from petbot.core.skills.base import Skill
from petbot.core.skills.context import Capabilities, EmbedSpec, SkillContext, SkillResult
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.music_skill import MusicSkill
from petbot.core.skills.registry import SkillRegistry
from petbot.frontends.interactions import app
from petbot.frontends.interactions.context import build_context
from petbot.frontends.interactions.handler import InteractionHandler
from petbot.frontends.interactions.render import (
    message_response,
    to_embed_dict,
    to_response_data,
)
from petbot.frontends.interactions.verify import verify_signature
from petbot.frontends.interactions.wire import CHANNEL_MESSAGE_WITH_SOURCE, PONG

TIMESTAMP = "1700000000"


def _keypair() -> tuple[SigningKey, str]:
    signing_key = SigningKey.generate()
    return signing_key, signing_key.verify_key.encode().hex()


def _sign(signing_key: SigningKey, body: bytes, *, timestamp: str = TIMESTAMP) -> str:
    return signing_key.sign(timestamp.encode() + body).signature.hex()


def _handler(
    public_key: str,
    *,
    skills: list[Skill] | None = None,
    skill_timeout: float = 2.5,
) -> InteractionHandler:
    registry = SkillRegistry(skills if skills is not None else [MathSkill()])
    return InteractionHandler(
        registry=registry,
        capabilities=Capabilities(supports_voice=False),
        public_key=public_key,
        skill_timeout=skill_timeout,
    )


class _FakeSkill(Skill):
    """A configurable skill for exercising the dispatch error paths."""

    name: ClassVar[str] = "fake"
    description: ClassVar[str] = "fake"
    input_schema: ClassVar[Mapping[str, Any]] = {
        "type": "object",
        "properties": {},
        "additionalProperties": True,
    }

    def __init__(
        self,
        *,
        result: SkillResult | None = None,
        exc: Exception | None = None,
        delay: float = 0.0,
    ) -> None:
        self._result = result if result is not None else SkillResult.message("ok")
        self._exc = exc
        self._delay = delay

    async def run(self, args: Mapping[str, Any], ctx: SkillContext) -> SkillResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exc is not None:
            raise self._exc
        return self._result


async def _dispatch_fake(skill: _FakeSkill, *, skill_timeout: float = 2.5) -> dict[str, Any]:
    signing_key, public_key = _keypair()
    handler = _handler(public_key, skills=[skill], skill_timeout=skill_timeout)
    body = json.dumps({"type": 2, "data": {"name": "fake"}}).encode()
    _, response = await handler.handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    return response


# --- verify -----------------------------------------------------------------


def test_verify_accepts_a_valid_signature() -> None:
    signing_key, public_key = _keypair()
    body = b'{"type":1}'
    assert verify_signature(public_key, TIMESTAMP, body, _sign(signing_key, body)) is True


def test_verify_rejects_a_tampered_body() -> None:
    signing_key, public_key = _keypair()
    signature = _sign(signing_key, b'{"type":1}')
    assert verify_signature(public_key, TIMESTAMP, b'{"type":2}', signature) is False


def test_verify_rejects_malformed_hex() -> None:
    _, public_key = _keypair()
    assert verify_signature(public_key, TIMESTAMP, b"{}", "not-hex") is False


# --- context ----------------------------------------------------------------


def test_build_context_from_guild_interaction() -> None:
    interaction = {
        "channel_id": "555",
        "channel": {"nsfw": True},
        "member": {"user": {"id": "7", "username": "tester", "global_name": "Tester"}},
    }
    ctx = build_context(interaction)
    assert ctx.user.id == "7"
    assert ctx.user.display_name == "Tester"
    assert ctx.capabilities.allows_explicit is True
    assert ctx.capabilities.supports_voice is False
    assert ctx.conversation_id == "discord:555"


def test_build_context_from_dm_defaults_to_sfw() -> None:
    ctx = build_context({"channel_id": "9", "user": {"id": "3", "username": "dm"}})
    assert ctx.user.id == "3"
    assert ctx.capabilities.allows_explicit is False


def test_conversation_id_falls_back_when_channel_missing() -> None:
    ctx = build_context({"id": "99", "user": {"id": "3", "username": "dm"}})
    assert ctx.conversation_id == "discord:interaction:99"


# --- render ------------------------------------------------------------------


def test_to_embed_dict_maps_fields() -> None:
    spec = EmbedSpec(title="t", description="d", url="u", color=255, image_url="i", author_name="a")
    embed = to_embed_dict(spec)
    assert embed["title"] == "t"
    assert embed["color"] == 255
    assert embed["image"] == {"url": "i"}
    assert embed["author"] == {"name": "a"}


def test_error_result_renders_as_content() -> None:
    data = to_response_data(SkillResult.failure("nope"))
    assert data == {"content": "nope"}


def test_message_response_carries_embed() -> None:
    response = message_response(SkillResult.message("hi", embed=EmbedSpec(title="t")))
    assert response["type"] == CHANNEL_MESSAGE_WITH_SOURCE
    assert response["data"]["content"] == "hi"
    assert response["data"]["embeds"][0]["title"] == "t"


def test_to_embed_dict_prunes_absent_fields() -> None:
    assert to_embed_dict(EmbedSpec(title="t")) == {"title": "t"}


def test_to_embed_dict_omits_empty_author_subfields() -> None:
    embed = to_embed_dict(EmbedSpec(author_name="a", author_url=""))
    assert embed["author"] == {"name": "a"}


def test_empty_result_gets_a_placeholder_not_empty_message() -> None:
    # A success with no text and no embed must not serialise to {} (Discord 400).
    data = to_response_data(SkillResult.message())
    assert data["content"]


def test_long_text_is_truncated_explicitly_not_silently() -> None:
    data = to_response_data(SkillResult.message("x" * 5000))
    content = data["content"]
    assert len(content) <= 2000
    assert "truncated" in content


# --- handler -----------------------------------------------------------------


async def test_ping_returns_pong() -> None:
    signing_key, public_key = _keypair()
    body = b'{"type":1}'
    status, response = await _handler(public_key).handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    assert status == 200
    assert response == {"type": PONG}


async def test_invalid_signature_is_401() -> None:
    _, public_key = _keypair()
    status, response = await _handler(public_key).handle(
        b'{"type":1}', signature="00", timestamp=TIMESTAMP
    )
    assert status == 401
    assert "error" in response


async def test_missing_signature_is_401() -> None:
    _, public_key = _keypair()
    status, _ = await _handler(public_key).handle(b"{}", signature=None, timestamp=None)
    assert status == 401


async def test_unparseable_body_is_400() -> None:
    signing_key, public_key = _keypair()
    body = b"not json"
    status, _ = await _handler(public_key).handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    assert status == 400


async def test_math_command_dispatches_to_skill() -> None:
    signing_key, public_key = _keypair()
    payload = {
        "type": 2,
        "channel_id": "1",
        "data": {"name": "math", "options": [{"name": "expression", "value": "2*21"}]},
    }
    body = json.dumps(payload).encode()
    status, response = await _handler(public_key).handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    assert status == 200
    assert response["type"] == CHANNEL_MESSAGE_WITH_SOURCE
    assert "42" in response["data"]["content"]


async def test_ping_command_is_adapter_level() -> None:
    signing_key, public_key = _keypair()
    body = json.dumps({"type": 2, "data": {"name": "ping"}}).encode()
    _, response = await _handler(public_key).handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    assert "Pong" in response["data"]["content"]


async def test_voice_skill_is_not_exposed() -> None:
    signing_key, public_key = _keypair()
    handler = _handler(public_key, skills=[MathSkill(), MusicSkill()])
    body = json.dumps({"type": 2, "data": {"name": "music"}}).encode()
    _, response = await handler.handle(
        body, signature=_sign(signing_key, body), timestamp=TIMESTAMP
    )
    # supports_voice=False hides /music; it is reported as unavailable.
    assert "isn't available" in response["data"]["content"]


async def test_slow_skill_times_out_with_a_clear_message() -> None:
    response = await _dispatch_fake(_FakeSkill(delay=0.2), skill_timeout=0.02)
    assert "too long" in response["data"]["content"]


async def test_unexpected_skill_exception_is_caught() -> None:
    response = await _dispatch_fake(_FakeSkill(exc=RuntimeError("boom")))
    assert "went wrong" in response["data"]["content"]


# --- app (composition root + Lambda entrypoint) ------------------------------


async def test_build_handler_builds_from_settings() -> None:
    settings = InteractionsSettings(_env_file=None, discord_public_key="ab12")
    async with httpx.AsyncClient() as client:
        handler = app.build_handler(settings, http_client=client)
    assert isinstance(handler, InteractionHandler)


def test_lambda_handler_answers_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    signing_key, public_key = _keypair()
    # The Lambda needs only the public key — no bot token on this path.
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", public_key)
    monkeypatch.setattr(app, "_settings", None)  # rebuild the cached cold-start settings
    body = '{"type":1}'
    event = {
        "headers": {
            "X-Signature-Ed25519": _sign(signing_key, body.encode()),
            "X-Signature-Timestamp": TIMESTAMP,
        },
        "body": body,
        "isBase64Encoded": False,
    }
    response = app.lambda_handler(event)
    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"type": PONG}
