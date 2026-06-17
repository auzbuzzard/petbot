# ADR 0002: Defer the LLM layer behind a provider-agnostic seam

- Status: Superseded by [ADR 0007](0007-llm-agent-pydantic-ai.md) (2026-06-17)
- Date: 2026-05-30

> The deferral is over: the LLM layer landed in 2.1 as the `chat` skill (a
> pydantic-ai agent whose tools are the sibling skills), provider-agnostic via
> `CHAT_PROVIDER` (Bedrock / OpenRouter). See ADR 0007.

## Context

An LLM "agent" layer is a wanted feature but is cost-sensitive and the provider
choice is not yet made. Building it now would risk premature lock-in to one
vendor and slow down the core revival.

## Decision

**Defer** the LLM layer to a later phase, but design so it drops in without
rework:

- It will live in the neutral core (e.g. `petbot/core/llm/`), like skills.
- A provider-agnostic interface (an adapter per provider — OpenAI-compatible,
  Gemini, local via Ollama, etc.) will keep the provider a config choice.
- The function-calling loop will read the existing `SkillRegistry`, format each
  skill's `input_schema` into the provider's tool format, dispatch to
  `skill.run(...)`, and return a `SkillResult` — the same neutral entry point
  every frontend already uses.
- Sessions will key off the neutral `conversation_id` already on `SkillContext`.

## Consequences

- No LLM SDK is a dependency today.
- Skills already expose everything the loop needs (`input_schema`, `run`), so the
  future work is genuinely additive.
- Conversational entry on Discord (@mention/thread) will require enabling the
  Message Content intent at that point.
