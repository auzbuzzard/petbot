"""Build the pydantic-ai model from :class:`ChatSettings` — the only vendor-aware spot.

Kept apart from the agent so the agent stays provider-agnostic and tests can run
the agent against ``TestModel`` without importing any SDK.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from petbot.skills.chat.settings import ChatSettings


def build_model(settings: ChatSettings) -> Model:
    """Construct the configured LLM model. Settings validation already guaranteed a
    model id and (for OpenRouter) an API key, so no defensive guards are needed here."""
    if settings.provider == "openrouter":
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        assert settings.openrouter_api_key is not None  # guaranteed by ChatSettings validator
        provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
        return OpenAIChatModel(settings.model, provider=provider)

    from pydantic_ai.models.bedrock import BedrockConverseModel

    return BedrockConverseModel(settings.model)
