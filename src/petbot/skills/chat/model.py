"""Build the pydantic-ai model from :class:`ChatSettings` — the only vendor-aware spot.

Kept apart from the agent so the agent stays provider-agnostic and tests can run
the agent against ``TestModel`` without importing any SDK.
"""

from __future__ import annotations

from typing import assert_never

from pydantic_ai.models import Model

from petbot.skills.chat.settings import BedrockModel, ChatSettings, OpenRouterModel


def build_model(settings: ChatSettings) -> Model:
    """Construct the configured LLM model from the discriminated provider config."""
    match settings.llm:
        case OpenRouterModel(model=model, api_key=api_key):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider

            return OpenAIChatModel(model, provider=OpenRouterProvider(api_key=api_key))
        case BedrockModel(model=model):
            from pydantic_ai.models.bedrock import BedrockConverseModel

            return BedrockConverseModel(model)
        case _:
            assert_never(settings.llm)
