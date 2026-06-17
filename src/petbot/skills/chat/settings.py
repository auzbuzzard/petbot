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

#: The default persona. It is product copy, not logic, so it ships as a default
#: that operators can override per deployment via ``CHAT_SYSTEM_PROMPT`` (a long
#: prompt is fine in an env var; for very long prompts, point it at a file's
#: contents at the call site).
DEFAULT_SYSTEM_PROMPT = (
    "You are PetBot, a friendly, slightly mischievous pet companion in a Discord "
    "server. Keep replies short and warm. When a user wants a calculation or an "
    "image from Derpibooru or e621, call the matching tool rather than guessing. "
    "Never describe explicit content in text; just present what the tool returns."
)


class ChatSettings(BaseSettings):
    """Which LLM the chat agent talks to, and how to reach it."""

    model_config = SettingsConfigDict(
        env_prefix="chat_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # Every field below is a default, overridable from the environment
    # (``CHAT_PROVIDER``, ``CHAT_BEDROCK_MODEL``, ``CHAT_OPENROUTER_MODEL``, …) —
    # no model id is fixed in code.
    provider: ChatProvider = "bedrock"
    #: Bedrock model id default (used when ``provider == "bedrock"``).
    bedrock_model: str = "amazon.nova-lite-v1:0"
    #: OpenRouter model id default (used when ``provider == "openrouter"``); a
    #: current free Gemma 3 checkpoint for zero-cost local development.
    openrouter_model: str = "google/gemma-3-27b-it:free"
    #: OpenRouter API key; required only when ``provider == "openrouter"``.
    openrouter_api_key: str | None = None
    #: The agent's persona; overridable via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
