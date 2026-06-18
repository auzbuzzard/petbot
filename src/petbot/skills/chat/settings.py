"""The chat worker's model configuration.

Provider-agnostic by design (no vendor lock-in): the same agent runs against
Bedrock or an OpenAI-compatible endpoint (OpenRouter), chosen by ``CHAT_PROVIDER``.
The model id is a **required** setting (``CHAT_MODEL``) — there is no model name in
code, and a missing or provider-inconsistent config fails fast at construction.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import model_validator
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
    #: The model id for the chosen provider (``CHAT_MODEL``). Required — no default,
    #: no ``None``: a worker without a model id can't run, so it fails fast.
    model: str
    #: OpenRouter API key — genuinely optional (Bedrock never uses it), but required
    #: when ``provider == "openrouter"`` (enforced below).
    openrouter_api_key: str | None = None
    #: The agent's persona; overridable via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = DEFAULT_SYSTEM_PROMPT

    @model_validator(mode="after")
    def _require_openrouter_key(self) -> Self:
        if self.provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("CHAT_PROVIDER=openrouter requires CHAT_OPENROUTER_API_KEY.")
        return self
