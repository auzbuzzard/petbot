"""Build a pydantic-ai model from a provider config — the only vendor-aware spot.

Kept apart from the agent so the agent stays provider-agnostic and tests can run
the agent against ``TestModel`` without importing any SDK. The same builder serves
both roles: the tool-calling agent (:attr:`ChatSettings.llm`) and the slash-path
stylizer (:meth:`ChatSettings.stylizer_llm`), since both are the same ``LLMConfig`` union.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, assert_never

from pydantic_ai.models import Model
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.profiles.google import GoogleJsonSchemaTransformer
from pydantic_ai.profiles.openai import OpenAIModelProfile, openai_model_profile

from petbot.process.settings import (
    BedrockMantleModel,
    BedrockModel,
    ChatSettings,
    LLMConfig,
    OpenAICompatibleModel,
    OpenRouterModel,
)


class _GeminiToolSchema(GoogleJsonSchemaTransformer):
    def __init__(self, schema: dict[str, Any], *, strict: bool | None = None) -> None:
        super().__init__(
            schema, strict=strict, prefer_inlined_defs=True, simplify_nullable_unions=True
        )


def _openai_compatible_profile(model_name: str) -> ModelProfile | None:
    """The chat-model profile for a model reached over an OpenAI-compatible endpoint, chosen
    by **model identity** rather than by which provider connects.

    pydantic-ai derives the profile from the *provider*: ``OpenRouterProvider`` sniffs the
    ``google/`` prefix and applies Gemma-aware schema handling, but a generic
    ``OpenAIProvider`` (how we reach Gemma 4 on Bedrock's ``mantle`` endpoint) cannot know the
    model behind a custom base URL is Gemma, so it falls back to the plain OpenAI profile and
    sends Gemma schemas it rejects. We pin the profile here so dev (OpenRouter) and prod
    (mantle) drive the *same* model identically — the "config flip" the architecture intends.

    Strict tool definitions are switched *off* on this path. They are an OpenAI-platform
    feature whose validator requires every declared property to appear in ``required`` (an
    optional argument is expressed as required-and-nullable). A Gemini-subset schema says the
    opposite: optionals stay out of ``required`` and carry ``"nullable": true``. Advertising
    strict while sending the Google dialect makes an endpoint that enforces it reject the whole
    request — ``invalid_function_parameters: Invalid schema for function 'derpi': 'sort' is
    required by being declared in 'properties' but not present in 'required'`` — which fails
    every chat turn, not just one that would call the tool. The dialect Gemma needs is the one
    we keep; strict is what gives.

    Gemma 4 and Gemini can think, so the profile declares ``supports_thinking``. Without it
    pydantic-ai silently drops the unified ``thinking`` setting (``CHAT_THINKING``).
    """
    name = model_name.lower()
    if "gemma" in name or "gemini" in name:
        # `from_profile` re-types the provider's profile as the OpenAI one, so the strict flag
        # (an `openai_`-prefixed field) is settable and type-checked rather than smuggled in.
        return replace(
            OpenAIModelProfile.from_profile(openai_model_profile(model_name)),
            json_schema_transformer=_GeminiToolSchema,
            openai_supports_strict_tool_definition=False,
            supports_thinking=True,
            openai_chat_send_back_thinking_parts=False,
        )
    return None


def build_model_from_config(llm: LLMConfig) -> Model:
    match llm:
        case OpenRouterModel(model=model, api_key=api_key):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openrouter import OpenRouterProvider

            return OpenAIChatModel(
                model,
                provider=OpenRouterProvider(api_key=api_key),
                profile=_openai_compatible_profile(model),
            )
        case OpenAICompatibleModel(model=model, base_url=base_url, api_key=api_key):
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            return OpenAIChatModel(
                model,
                provider=OpenAIProvider(base_url=base_url, api_key=api_key),
                profile=_openai_compatible_profile(model),
            )
        case BedrockMantleModel(model=model, base_url=base_url):
            from pydantic_ai.models import create_async_http_client
            from pydantic_ai.models.openai import OpenAIChatModel
            from pydantic_ai.providers.openai import OpenAIProvider

            from petbot.process.sigv4 import MANTLE_SERVICE, SigV4Auth, mantle_region

            http_client = create_async_http_client()
            http_client.auth = SigV4Auth(MANTLE_SERVICE, mantle_region(base_url))
            # The OpenAI client insists on a key; SigV4Auth replaces the header it makes.
            return OpenAIChatModel(
                model,
                provider=OpenAIProvider(
                    base_url=base_url, api_key="sigv4", http_client=http_client
                ),
                profile=_openai_compatible_profile(model),
            )
        case BedrockModel(model=model):
            from pydantic_ai.models.bedrock import BedrockConverseModel

            return BedrockConverseModel(model)
        case _:
            assert_never(llm)


def build_model(settings: ChatSettings) -> Model:
    return build_model_from_config(settings.llm)
