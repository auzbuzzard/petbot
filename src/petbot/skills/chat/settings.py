"""The chat worker's model configuration.

Provider-agnostic (no vendor lock-in): the LLM is a **discriminated union**
(``CHAT_LLM__KIND`` selects the variant), so only the chosen provider's fields
exist — no model name in code, no ``str | None`` for conditionally-required
values. Set via nested env, e.g. ``CHAT_LLM__KIND=openrouter`` +
``CHAT_LLM__MODEL=…`` + ``CHAT_LLM__API_KEY=…``.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: The default persona — product copy, not logic, overridable via ``CHAT_SYSTEM_PROMPT``.
DEFAULT_SYSTEM_PROMPT = (
    "You are PetBot, a friendly, slightly mischievous pet companion in a Discord "
    "server. Keep replies short and warm. When a user wants a calculation or an "
    "image from Derpibooru or e621, call the matching tool rather than guessing. "
    "Never describe explicit content in text; just present what the tool returns."
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
    #: The agent's persona; overridable via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
