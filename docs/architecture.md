# Architecture

A thin, always-on Discord **edge** holds the gateway and runs no skills; it
dispatches every request to a **worker** that does. The codebase is one
installable package, `petbot`, under `src/`, with install-extras slicing
dependencies per process.

For the module map, the calling pattern, and the invariants, see
[`AGENTS.md`](../AGENTS.md). For the *why* behind the splits and the LLM layer:

- [ADR 0006](adr/0006-gateway-edge-microservice-skills.md) — the edge/worker
  split and why music is its own worker.
- [ADR 0007](adr/0007-llm-agent-pydantic-ai.md) — the chat agent (pydantic-ai),
  skills-as-tools, and the provider-agnostic model choice.
- [ADR 0003](adr/0003-neutral-core.md) — the neutral-core decision the
  `petbot.domain` kernel descends from.
- [ADR 0005](adr/0005-serverless-deployment.md) — serverless compute (the core
  worker's Lambda path).

## The request path

```
Discord ⇄ [ edge ]  --dispatch(JSON)-->  [ core worker ]  math · booru · chat(LLM)
          petbot.edge    transport          petbot.workers.core
                                              \--> [ music worker ]  gateway + voice
                                                    petbot.workers.music
```

1. The edge maps an @mention to a neutral `SkillContext` and calls
   `await skills.chat(ChatArgs(message), ctx)` on its typed `Skills` client
   (`SkillsClient` over a transport).
2. `SkillCall` carries the typed args. A `LocalTransport` runs the call
   in-process with no serialisation; a remote transport (`HttpTransport`,
   `LambdaTransport`) serialises at the boundary, and the worker validates the
   args against the skill's `args_model`. The chat skill's LLM tools are its
   sibling skills, called in-process through the same client.
3. The worker returns a neutral `SkillResult`; the edge renders it to Discord
   (the one place neutral results become `discord.Embed`/messages).

The dependency rules (kernel imports nothing else first-party; the edge never
imports a skill) are enforced by `lint-imports` — see `[tool.importlinter]` in
`pyproject.toml`.
