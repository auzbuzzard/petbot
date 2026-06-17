# Architecture

PetBot is **A3a**: a thin, always-on Discord **edge** that holds the gateway and
runs no skills, dispatching every request to a **worker** that does. The codebase
is one uv workspace of independently-installable packages under the `petbot.*`
namespace (PEP 420).

For the package map, the typed calling pattern, and the invariants, see
[`AGENTS.md`](../AGENTS.md). For the *why* behind the splits and the LLM layer,
see the ADRs:

- [ADR 0006](adr/0006-gateway-edge-microservice-skills.md) — the edge/worker
  (microservice skills) split and why music is its own worker.
- [ADR 0007](adr/0007-llm-agent-pydantic-ai.md) — the chat agent (pydantic-ai),
  skills-as-tools, and the provider-agnostic model choice.
- [ADR 0003](adr/0003-neutral-core.md) — the original neutral-core decision the
  `petbot.domain` kernel descends from (historical).
- [ADR 0005](adr/0005-serverless-deployment.md) — serverless compute (the brain
  worker's Lambda path).

## The request path

```
Discord ⇄ [ edge ]  --SkillCall(JSON)-->  [ brain worker ]  math · booru · chat(LLM)
          petbot.discord   Transport        petbot.workers.brain
                                              \--> [ music worker ]  gateway + voice
                                                    petbot.workers.music
```

1. The edge maps an @mention to a neutral `SkillContext` and calls
   `await skills.chat(ChatArgs(message), ctx)` on its typed `Skills` client
   (`RemoteSkills` over an HTTP or Lambda `Transport`).
2. The client serialises a `SkillCall`; the worker re-validates the args against
   the skill's `args_model` and runs it. The chat skill's LLM tools are its
   sibling skills (math/booru), called in-process via `LocalSkills`.
3. The worker returns a neutral `SkillResult`; the edge renders it to Discord
   (the one place neutral results become `discord.Embed`/messages).

The dependency rules (kernel imports nothing first-party; the edge never imports
a skill) are enforced by `lint-imports` — see `[tool.importlinter]` in
`pyproject.toml`.
