"""The chat process's model configuration.

Provider-agnostic (no vendor lock-in): the LLM is a **discriminated union**
(``CHAT_LLM__KIND`` selects the variant), so only the chosen provider's fields
exist — no model name in code, no ``str | None`` for conditionally-required
values. Set via nested env, e.g. ``CHAT_LLM__KIND=openrouter`` +
``CHAT_LLM__MODEL=…`` + ``CHAT_LLM__API_KEY=…``.

Two **roles**, both the same config union: ``llm`` is the tool-calling agent;
``stylizer`` is an optional cheaper model that restyles a finished result in PetBot's
voice for the LLM-free slash path (``CHAT_STYLIZER__KIND=…`` etc.). Unset ⇒ the
stylizer reuses ``llm``, so picking a cheaper tier is a config flip, not code.
"""

from __future__ import annotations

from importlib import resources
from typing import Annotated, Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _prompt(*names: str) -> str:
    """Join one or more prompt fragments shipped as package data (``prompts/*.md``).

    The persona is prose, not a Python constant — clean diffs, no escaping — and the
    shared ``persona.md`` fragment is composed into each role's prompt so the voice
    is defined once.
    """
    parts = (
        resources.files(__package__).joinpath("prompts", name).read_text(encoding="utf-8").strip()
        for name in names
    )
    return "\n\n".join(parts)


def _load_agent_prompt() -> str:
    """The conversational agent's prompt: shared persona + its tool-use and
    no-invented-reason rules. Overridable via ``CHAT_SYSTEM_PROMPT``."""
    return _prompt("persona.md", "agent.md")


def _load_stylizer_prompt() -> str:
    """The slash-path stylizer's prompt: the same persona + a faithful-rewrite
    instruction. Overridable via ``CHAT_STYLIZER_PROMPT``."""
    return _prompt("persona.md", "stylizer.md")


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
    """Which LLM(s) the chat skill talks to, and how to reach them."""

    model_config = SettingsConfigDict(
        env_prefix="chat_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    #: The tool-calling agent's LLM (required; see ``CHAT_LLM__*``).
    llm: LLMConfig
    #: Optional cheaper model for the slash-path stylizer (``CHAT_STYLIZER__*``);
    #: unset ⇒ reuse :attr:`llm`. Resolved by :meth:`stylizer_llm`.
    stylizer: LLMConfig | None = None
    #: The agent's persona + rules (``prompts/persona.md`` + ``agent.md``); override
    #: via ``CHAT_SYSTEM_PROMPT``.
    system_prompt: str = Field(default_factory=_load_agent_prompt)
    #: The stylizer's persona + rewrite rule (``persona.md`` + ``stylizer.md``);
    #: override via ``CHAT_STYLIZER_PROMPT``.
    stylizer_prompt: str = Field(default_factory=_load_stylizer_prompt)

    def stylizer_llm(self) -> LLMConfig:
        """The stylizer's model config: its own if set, else the agent's (one tier)."""
        return self.stylizer or self.llm
