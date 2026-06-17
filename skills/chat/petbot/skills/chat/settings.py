"""The chat worker's model configuration.

Provider-agnostic by design (no vendor lock-in): the same agent runs against
Bedrock in prod and an OpenAI-compatible endpoint (OpenRouter) in dev, chosen by
``CHAT_PROVIDER``. Model ids are configuration, never hard-coded — so swapping to
a cheaper/free model is an env change, not a code change.

Defaults: Bedrock → Amazon Nova Lite (cheap, always-available on Bedrock; note
Bedrock does **not** host Google's Gemma — use OpenRouter for that). OpenRouter →
a free Gemma checkpoint, handy for zero-cost local development.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ChatProvider = Literal["bedrock", "openrouter"]


class ChatSettings(BaseSettings):
    """Which LLM the chat agent talks to, and how to reach it."""

    model_config = SettingsConfigDict(
        env_prefix="chat_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    provider: ChatProvider = "bedrock"
    #: Bedrock model id (used when ``provider == "bedrock"``).
    bedrock_model: str = "amazon.nova-lite-v1:0"
    #: OpenRouter model id (used when ``provider == "openrouter"``).
    openrouter_model: str = "google/gemma-2-9b-it:free"
    #: OpenRouter API key; required only when ``provider == "openrouter"``.
    openrouter_api_key: str | None = None
