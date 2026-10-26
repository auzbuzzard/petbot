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
from pydantic_ai.settings import ThinkingLevel
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
    return _prompt("persona.md", "agent.md")


def _load_stylizer_prompt() -> str:
    return _prompt("persona.md", "stylizer.md")


class BedrockModel(BaseModel):
    kind: Literal["bedrock"] = "bedrock"
    model: str


class OpenRouterModel(BaseModel):
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


class BedrockMantleModel(BaseModel):
    """Bedrock's OpenAI-compatible ``bedrock-mantle`` endpoint, authenticated with the
    runtime's own AWS credentials (SigV4) instead of an API key.

    ``base_url`` is the endpoint, e.g. ``https://bedrock-mantle.us-east-1.api.aws/openai/v1``;
    requests are signed for the Region in its host. The caller's IAM identity needs
    ``bedrock-mantle:CreateInference``: no key exists to mint, store or rotate.
    """

    kind: Literal["bedrock_mantle"] = "bedrock_mantle"
    model: str
    base_url: str


LLMConfig = Annotated[
    BedrockModel | OpenRouterModel | OpenAICompatibleModel | BedrockMantleModel,
    Field(discriminator="kind"),
]


class SlidingWindowContext(BaseModel):
    kind: Literal["sliding_window"] = "sliding_window"


class SummarizeContext(BaseModel):
    kind: Literal["summarize"] = "summarize"


#: How the chat process compacts history *when the model rejects it for length* — the
#: strategy is reactive (the provider is the trigger), so it carries no budget/window
#: number. Tagged by ``kind`` (``CHAT_CONTEXT__KIND=summarize``).
ContextConfig = Annotated[SlidingWindowContext | SummarizeContext, Field(discriminator="kind")]


class ChatSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="chat_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
    )

    llm: LLMConfig
    stylizer: LLMConfig | None = None
    system_prompt: str = Field(default_factory=_load_agent_prompt)
    stylizer_prompt: str = Field(default_factory=_load_stylizer_prompt)
    context: ContextConfig = Field(default_factory=SlidingWindowContext)
    thinking: ThinkingLevel | None = None

    def stylizer_llm(self) -> LLMConfig:
        return self.stylizer or self.llm
