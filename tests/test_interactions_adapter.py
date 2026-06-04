"""Tests for the HTTP-Interactions frontend (offline; no HTTP server, no network).

Signatures are exercised with a real Ed25519 keypair generated per test, so the
verification path is genuinely tested rather than stubbed.
"""

from __future__ import annotations

import json

import httpx
import pytest
from nacl.signing import SigningKey

from petbot.config import ConfigError, Settings
from petbot.core.skills.base import Skill
from petbot.core.skills.context import Capabilities, EmbedSpec, SkillResult
from petbot.core.skills.math_skill import MathSkill
from petbot.core.skills.music_skill import MusicSkill
from petbot.core.skills.registry import SkillRegistry
from petbot.frontends.interactions import app
from petbot.frontends.interactions.context import build_context
from petbot.frontends.interactions.handler import InteractionHandler
from petbot.frontends.interactions.render import (
    chunk_text,
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


def _handler(public_key: str, *, skills: list[Skill] | None = None) -> InteractionHandler:
    registry = SkillRegistry(skills if skills is not None else [MathSkill()])
    return InteractionHandler(
        registry=registry,
        capabilities=Capabilities(supports_voice=False),
        public_key=public_key,
    )


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


def test_chunk_text_splits_on_limit() -> None:
    text = "\n".join("x" * 50 for _ in range(10))  # 10 lines, 50 chars each
    chunks = chunk_text(text, limit=120)
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert "".join(chunks) == text


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


# --- app (composition root + Lambda entrypoint) ------------------------------


async def test_build_handler_requires_public_key() -> None:
    async with httpx.AsyncClient() as client:
        with pytest.raises(ConfigError, match="DISCORD_PUBLIC_KEY"):
            app.build_handler(Settings(discord_token="x"), http_client=client)


def test_lambda_handler_answers_ping(monkeypatch: pytest.MonkeyPatch) -> None:
    signing_key, public_key = _keypair()
    monkeypatch.setenv("DISCORD_TOKEN", "x")
    monkeypatch.setenv("DISCORD_PUBLIC_KEY", public_key)
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
