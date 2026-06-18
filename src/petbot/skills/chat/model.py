"""Build the pydantic-ai model from :class:`ChatSettings` — the only vendor-aware spot.

Kept apart from the agent so the agent stays provider-agnostic and tests can run
the agent against ``TestModel`` without importing any SDK.
"""

from __future__ import annotations

from pydantic_ai.models import Model

from petbot.skills.chat.settings import ChatSettings


def build_model(settings: ChatSettings) -> Model:
    """Construct the configured LLM model, failing fast on missing deployment config."""
    if settings.provider == "openrouter":
        if not settings.openrouter_api_key:
            raise RuntimeError("CHAT_PROVIDER=openrouter requires CHAT_OPENROUTER_API_KEY.")
        if not settings.openrouter_model:
            raise RuntimeError("CHAT_PROVIDER=openrouter requires CHAT_OPENROUTER_MODEL.")
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openrouter import OpenRouterProvider

        provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
        return OpenAIChatModel(settings.openrouter_model, provider=provider)

    if not settings.bedrock_model:
        raise RuntimeError("CHAT_PROVIDER=bedrock requires CHAT_BEDROCK_MODEL.")

    from pydantic_ai.models.bedrock import BedrockConverseModel

    return BedrockConverseModel(settings.bedrock_model)
