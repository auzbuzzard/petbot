# Architecture

PetBot is a chatbot: **`input → process → output`**. A thin, always-on Discord
**frontend** holds the gateway and runs no skills; it dispatches every request to a
**compute service** that runs the process. The codebase is one installable package,
`petbot`, under `src/`, organised **by concept** (and deployed **by service**), with
install-extras slicing dependencies per process.

For the module map, the calling pattern, and the invariants, see
[`AGENTS.md`](../AGENTS.md). For the *why* behind the splits:

- [ADR 0009](adr/0009-process-pipeline.md) — the process pipeline: the `Input` sum
  type, the `Process` verb (chat / command), the `ToolRegistry`, errors-as-exceptions,
  and the concept/service organisation. **The current end state.**
- [ADR 0006](adr/0006-gateway-edge-microservice-skills.md) — the original frontend +
  compute split and why music is its own service (vocabulary reshaped by 0009).
- [ADR 0007](adr/0007-llm-agent-pydantic-ai.md) — the chat agent (pydantic-ai),
  skills-as-tools, and the provider-agnostic model choice.
- [ADR 0003](adr/0003-neutral-core.md) — the neutral-core decision the `petbot.domain`
  kernel descends from.
- [ADR 0005](adr/0005-serverless-deployment.md) — serverless compute (the core
  service's Lambda path).

## The request path

```
Discord ⇄ [ frontend ]  --Input(JSON)-->  [ core service ]  chat(LLM) · math · booru
            petbot.frontends.discord  transport  petbot.services.core
                                                  \--> [ music service ]  gateway + voice
                                                        petbot.services.music
```

1. The frontend maps an `@mention` to a `TextInput` (and a slash command to a
   `CommandInput`) plus a neutral `SkillContext`, and calls
   `await process.respond(inp, ctx)` on its `ProcessClient` (a `Process` over a
   transport).
2. A `Dispatch` envelope carries the typed input. A remote transport
   (`HttpTransport`, `LambdaTransport`) serialises it at the boundary; `serve` decodes
   it on the compute side.
3. A `RouterProcess` picks — by the input *type*, the one place anything branches —
   the **chat process** (the pydantic-ai brain, which voices itself) or the **command
   process** (which runs the resolved tool and applies the persona `StylePort`). Tools
   are called in-process through the `ToolRegistry`; the agent's tools and the slash
   surface both derive from one `CATALOG`.
4. The service returns a neutral `SkillResult`; the frontend renders it (the one place
   neutral results become `discord.Embed`/messages). An expected failure is **raised**
   as a `SkillError` and voiced once at the process output boundary — there is no error
   channel on the result.

The dependency rules (the kernel imports nothing else first-party; the frontend never
imports a skill or the process core; the process core never imports a concrete skill)
are enforced by `lint-imports` — see `[tool.importlinter]` in `pyproject.toml`.
