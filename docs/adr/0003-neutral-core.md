# ADR 0003: A platform-neutral core (ports & adapters)

- Status: Accepted
- Date: 2026-05-30

## Context

Two future directions are explicitly in scope but not built now: additional
frontends (Telegram, web) and the LLM layer (ADR 0002). We want those to be
additive, not rewrites, and we want to hedge the Discord-library bus factor
(ADR 0001).

## Decision

Split the codebase into a **platform-neutral core** (`petbot.core`) and
**adapters** (`petbot.frontends.*`), with a strict one-way dependency:

- The core speaks only neutral value objects — `SkillContext` in, `SkillResult`
  out — and exposes ports (e.g. `VoicePort`) that adapters implement.
- Skills branch on `Capabilities` flags, never on the platform.
- Rendering and message chunking live in the adapter, not the core.
- The core must not import `discord` or any frontend. This is enforced by
  `import-linter` and a unit test (`tests/test_core_isolation.py`).

## Consequences

- New frontends and the LLM layer plug into the same `SkillRegistry`/`Skill`
  contract without touching existing skills.
- A `discord.py` → fork swap is confined to `frontends/discord/`.
- Slight upfront cost: neutral DTOs and ports instead of using `discord` types
  directly. We implement **only** the Discord adapter now — no speculative
  Telegram/web scaffolding.
