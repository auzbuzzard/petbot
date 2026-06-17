# ADR 0007: The LLM agent — pydantic-ai, skills as tools, provider-agnostic

- Status: Accepted
- Date: 2026-06-17
- Supersedes the deferral in [ADR 0002](0002-deferred-llm.md); builds on the
  edge/worker split in [ADR 0006](0006-gateway-edge-microservice-skills.md).

## Context

2.1 lands the conversational layer (#15): users @mention PetBot and talk to it,
and the conversation can trigger the existing skills. The provider choice had to
stay open (cost-sensitive, no vendor lock-in), and the integration had to be
clean and typed rather than a hand-rolled function-calling loop.

## Decision

Implement chat as a normal skill — `petbot.skills.chat` — built on **pydantic-ai**:

- The agent's tools **are the sibling skills**. Each tool's argument type is the
  very same `petbot.types.*Args` pydantic model the skill validates, so one
  declaration feeds the typed client, the worker's validation, and the LLM tool
  schema. Tool bodies dispatch through a `Skills` client (`LocalSkills` in the
  brain worker — an in-process hop, no wire round-trip).
- The model is **provider-agnostic**, chosen by `CHAT_PROVIDER`: Amazon Bedrock
  for prod (a real, cheap on-Bedrock model — note Bedrock does *not* host Gemma),
  an OpenAI-compatible endpoint (OpenRouter, with free models like Gemma) for dev.
  Model ids are configuration, never code.
- The chat skill folds the model's prose plus any rich card a tool produced (a
  booru image) into a single neutral `SkillResult`, so the edge renders it
  exactly like any other result.

The chat skill runs in the **brain worker** alongside math + booru; the edge only
calls `skills.chat(...)`. Tests drive the agent with pydantic-ai's `TestModel` /
`FunctionModel`, so CI exercises the tool-calling path with no live LLM and no
secrets.

## Consequences

- Adding a tool to the agent is adding a skill (ADR 0006's recipe) plus one
  `@agent.tool` wrapper — no bespoke schema plumbing.
- Swapping providers/models is an env change. Free dev models keep cost at zero.
- The privileged **Message Content** intent is now required on the edge (chat
  reads message text); slash commands alone would not need it.
