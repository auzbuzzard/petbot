"""Build a pydantic-ai model from a provider config — the only vendor-aware spot.

Kept apart from the agent so the agent stays provider-agnostic and tests can run
the agent against ``TestModel`` without importing any SDK. The same builder serves
both roles: the tool-calling agent (:attr:`ChatSettings.llm`) and the slash-path
stylizer (:meth:`ChatSettings.stylizer_llm`), since both are the same ``LLMConfig`` union.
"""

from __future__ import annotations

from typing import assert_never

from pydantic_ai.models import Model

from petbot.skills.chat.settings import (
    BedrockModel,
    ChatSettings,
    LLMConfig,
    OpenAICompatibleModel,
    OpenRouterModel,
)


def build_model_from_config(llm: LLMConfig) -> Model:
    """Construct an LLM model from one discriminated provider config (either role)."""
    match llm:
        case OpenRouterModel(model=model, api_key=api_key):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider

            return OpenAIChatModel(model, provider=OpenRouterProvider(api_key=api_key))
        case OpenAICompatibleModel(model=model, base_url=base_url, api_key=api_key):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(
                model, provider=OpenAIProvider(base_url=base_url, api_key=api_key)
            )
        case BedrockModel(model=model):
            from pydantic_ai.models.bedrock import BedrockConverseModel

            return BedrockConverseModel(model)
        case _:
            assert_never(llm)


def build_model(settings: ChatSettings) -> Model:
    """The agent's model — the configured tool-calling provider (:attr:`llm`)."""
    return build_model_from_config(settings.llm)
