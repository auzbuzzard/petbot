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
    BedrockModel,
    ChatSettings,
    LLMConfig,
    OpenAICompatibleModel,
    OpenRouterModel,
)


class _GeminiToolSchema(GoogleJsonSchemaTransformer):
    """Gemini-subset JSON-schema transformer that also inlines ``$defs`` and collapses
    nullable unions — what Gemma needs to *see* a tool over an OpenAI-compatible endpoint.

    Gemma/Gemini accept only `a subset of OpenAPI v3.0.3
    <https://ai.google.dev/gemini-api/docs/function-calling>`_ for tool args: no ``title``,
    no ``$ref``/``$defs``, no ``anyOf`` nullable unions. The base
    :class:`GoogleJsonSchemaTransformer` pops the unsupported *keys*; the two constructor
    flags additionally inline ``$defs`` and rewrite ``str | None`` (an ``anyOf`` with
    ``null``) to ``{"nullable": true}``. Both come up in our ``*Args`` models (``BooruArgs``
    has optional fields), so without them Gemma receives a schema it can't parse, never sees
    the tool, and narrates a free-text call that leaks to the user instead of invoking it.
    """

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

    Returns ``None`` (defer to the provider default) for models we don't special-case.
    """
    name = model_name.lower()
    if "gemma" in name or "gemini" in name:
        # `from_profile` re-types the provider's profile as the OpenAI one, so the strict flag
        # (an `openai_`-prefixed field) is settable and type-checked rather than smuggled in.
        return replace(
            OpenAIModelProfile.from_profile(openai_model_profile(model_name)),
            json_schema_transformer=_GeminiToolSchema,
            openai_supports_strict_tool_definition=False,
        )
    return None


def build_model_from_config(llm: LLMConfig) -> Model:
    """Construct an LLM model from one discriminated provider config (either role)."""
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
        case BedrockModel(model=model):
            from pydantic_ai.models.bedrock import BedrockConverseModel

            return BedrockConverseModel(model)
        case _:
            assert_never(llm)


def build_model(settings: ChatSettings) -> Model:
    """The agent's model — the configured tool-calling provider (:attr:`llm`)."""
    return build_model_from_config(settings.llm)
