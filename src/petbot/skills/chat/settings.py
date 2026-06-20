"""The chat worker's model configuration.

Provider-agnostic (no vendor lock-in): the LLM is a **discriminated union**
(``CHAT_LLM__KIND`` selects the variant), so only the chosen provider's fields
exist — no model name in code, no ``str | None`` for conditionally-required
values. Set via nested env, e.g. ``CHAT_LLM__KIND=openrouter`` +
``CHAT_LLM__MODEL=…`` + ``CHAT_LLM__API_KEY=…``.
"""

from __future__ import annotations

from importlib import resources
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _load_default_system_prompt() -> str:
    """The default persona, shipped as package data (``prompts/system.md``) so it
    edits as prose — clean diffs, no Python escaping — and overrides via
    ``CHAT_SYSTEM_PROMPT``. Mirrors how the booru skill ships ``utterances.json``."""
    return (
        resources.files(__package__)
        .joinpath("prompts/system.md")
        .read_text(encoding="utf-8")
        .strip()
    )


class BedrockModel(BaseModel):
    """An Amazon Bedrock model."""

    kind: Literal["bedrock"] = "bedrock"
    model: str


class OpenRouterModel(BaseModel):
    """An OpenRouter (OpenAI-compatible) model."""

    kind: Literal["openrouter"] = "openrouter"
    model: str
    api_key: str


class OpenAICompatibleModel(BaseModel):
    """Any OpenAI-compatible chat endpoint, reached by base URL + API key.

    Covers AWS Bedrock's OpenAI-compatible ``bedrock-mantle`` endpoint (how Gemma 4
    is served — ``base_url=https://bedrock-mantle.<region>.api.aws/openai/v1``,
    ``api_key`` = a Bedrock API key), and equally a self-hosted Ollama/vLLM. The
    provider is just a URL + key, so new backends are config, not code.
    """

    kind: Literal["openai_compatible"] = "openai_compatible"
    model: str
    base_url: str
    api_key: str


#: Exactly one provider config, with only its own fields. Tagged by ``kind``.
LLMConfig = Annotated[
    BedrockModel | OpenRouterModel | OpenAICompatibleModel, Field(discriminator="kind")
]


class ChatSettings(BaseSettings):
    """Which LLM the chat agent talks to, and how to reach it."""

    model_config = SettingsConfigDict(
        env_prefix="chat_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    #: The LLM to use (required; see ``CHAT_LLM__*``).
    llm: LLMConfig
    #: The agent's persona (``prompts/system.md``); override via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = Field(default_factory=_load_default_system_prompt)
