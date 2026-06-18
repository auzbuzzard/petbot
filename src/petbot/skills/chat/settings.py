"""The chat worker's model configuration.

Provider-agnostic by design (no vendor lock-in): the same agent runs against
Bedrock or an OpenAI-compatible endpoint (OpenRouter), chosen by ``CHAT_PROVIDER``.
**No model id lives in code** — the deployment supplies it (``CHAT_BEDROCK_MODEL``
or ``CHAT_OPENROUTER_MODEL``), and a missing one fails fast in :func:`build_model`.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

ChatProvider = Literal["bedrock", "openrouter"]

#: The default persona — product copy, not logic, so it ships as a default that a
#: deployment can override via ``CHAT_SYSTEM_PROMPT``.
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

    provider: ChatProvider = "bedrock"
    #: Bedrock model id (required when ``provider == "bedrock"``) — set via
    #: ``CHAT_BEDROCK_MODEL``; never defaulted in code.
    bedrock_model: str | None = None
    #: OpenRouter model id (required when ``provider == "openrouter"``) — set via
    #: ``CHAT_OPENROUTER_MODEL``; never defaulted in code.
    openrouter_model: str | None = None
    #: OpenRouter API key (required when ``provider == "openrouter"``).
    openrouter_api_key: str | None = None
    #: The agent's persona; overridable via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
