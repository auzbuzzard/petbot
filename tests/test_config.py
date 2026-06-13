"""Tests for the pydantic-settings config: per-frontend requirements and parsing.

Constructed with ``_env_file=None`` so a developer's real ``.env`` never leaks
into the assertions; required values are passed as explicit kwargs (which outrank
env), and ``monkeypatch`` clears anything a stray shell export might supply.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from petbot.config import AppSettings, GatewaySettings, InteractionsSettings

# --- per-frontend requirements -----------------------------------------------


def test_gateway_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    with pytest.raises(ValidationError):
        GatewaySettings(_env_file=None)


def test_gateway_accepts_token_and_parses_guild() -> None:
    settings = GatewaySettings(_env_file=None, discord_token="t", dev_guild_id="123")
    assert settings.discord_token == "t"
    assert settings.dev_guild_id == 123


def test_gateway_blank_guild_is_none() -> None:
    settings = GatewaySettings(_env_file=None, discord_token="t", dev_guild_id="")
    assert settings.dev_guild_id is None


def test_gateway_rejects_non_integer_guild() -> None:
    with pytest.raises(ValidationError):
        GatewaySettings(_env_file=None, discord_token="t", dev_guild_id="abc")


def test_interactions_boots_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    # The #38 guarantee: the Lambda needs only the public key, never the bot token.
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    settings = InteractionsSettings(_env_file=None, discord_public_key="ab12")
    assert settings.discord_public_key == "ab12"


def test_interactions_requires_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DISCORD_PUBLIC_KEY", raising=False)
    with pytest.raises(ValidationError):
        InteractionsSettings(_env_file=None)


# --- shared parsing ----------------------------------------------------------


def test_booru_creds_default_to_none() -> None:
    settings = AppSettings(_env_file=None)
    assert settings.e621_username is None
    assert settings.derpibooru_api_key is None


def test_blank_optional_is_none() -> None:
    settings = AppSettings(_env_file=None, e621_api_key="")
    assert settings.e621_api_key is None


def test_log_defaults() -> None:
    settings = AppSettings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.log_format is None
    assert settings.resolved_log_format == "plain"


def test_prod_defaults_to_json() -> None:
    settings = AppSettings(_env_file=None, env="prod")
    assert settings.is_prod is True
    assert settings.resolved_log_format == "json"


def test_explicit_log_format_wins_and_is_normalised() -> None:
    settings = AppSettings(_env_file=None, env="prod", log_format="Plain")
    assert settings.log_format == "plain"  # case-normalised; explicit wins over env
    assert settings.resolved_log_format == "plain"


def test_rejects_bad_log_format() -> None:
    with pytest.raises(ValidationError):
        AppSettings(_env_file=None, log_format="yaml")
