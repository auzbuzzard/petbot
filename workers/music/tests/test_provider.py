"""The voice provider's conversation-id parsing (gateway resolution is smoke-only)."""

from __future__ import annotations

from petbot.workers.music.provider import _channel_id


def test_channel_id_parses_discord_conversation() -> None:
    assert _channel_id("discord:12345") == 12345


def test_channel_id_rejects_non_numeric() -> None:
    assert _channel_id("discord:abc") is None
    assert _channel_id("nope") is None
