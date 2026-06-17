# ADR 0006: Single gateway edge + microservice skills (reimagined architecture)

- Status: Accepted
- Date: 2026-06-17

## Context

Adding conversational LLM chat (#15): a user `@mention`s PetBot and it
answers, invoking skills through a tool-calling loop. Designing that forced a
deployment question ADR 0005 had deferred, and the answer **reverses ADR 0005's
ingress decision** and reshapes the repo.

Hard facts that drive the design:

1. **`@mention`/message content, presence/activity status, and voice are
   Gateway-only.** Discord delivers them solely over a persistent WebSocket
   (the Gateway); HTTP Interactions never receive them, and Discord has no
   outgoing-webhook for gateway events (and no IPv6). So conversational chat
   **requires an always-on process holding a Gateway connection** — it cannot be
   serverless.
2. **Setting an Interactions Endpoint URL diverts *all* slash interactions off
   the Gateway** (one app, "Option C"). A given command is XOR: HTTP *or*
   Gateway, never both — there is no redundancy to exploit.
3. Once an always-on Gateway holder exists for `@mention`, **ADR 0005's reason
   for the serverless HTTP-Interactions front door evaporates** — its premise was
   "no command needs an always-on process." That premise no longer holds.
4. The current frontends conflate **transport** (holding the connection) with
   **compute** (running every skill in-process). The neutral core makes skills
   *portable*, but the deployment unit is a per-frontend **monolith**: the Gateway
   adapter wires real skills into hand-written per-skill cogs; the Lambda adapter
   runs every skill in-process. That conflation is the thing this ADR removes.

## Decision

### 1. Topology — a minimal Gateway *edge* + dispatched microservice compute

A single **Gateway edge** is the only Discord-facing transport (slash +
`@mention` + presence + voice signalling). The edge is **dumb**: it holds the
WebSocket, sets presence, maps each event to a neutral request, and **dispatches**
it to decoupled compute over a neutral `DispatchPort`. It runs **no skill logic**
and carries **no skill dependencies**.

- **Ingress is unified** on the Gateway. The HTTP-Interactions path is removed
  (see §6) — slash commands arrive as `INTERACTION_CREATE` over the WebSocket
  because no Interactions Endpoint URL is set.
- **Compute is microservice.** Each skill (and the LLM agent) runs in a worker,
  reached via `DispatchPort`. The edge formats commands and offers LLM tools from
  a **manifest** (skill metadata as data), never by importing skills.
- This keeps the two wins independent: *one* Discord ingress (no duplicate command
  surface), and *N* independently deployable compute units.

### 2. Compute granularity — architecture full, runtime phased

The architecture is full microservice (clean per-skill boundaries); the **runtime
is consolidated** until scale justifies splitting:

- Skills are independently deployable **entry-point plugins**, but **deploy
  grouped**: one core worker hosts the stateless skills + the chat agent.
- **`/music` is the one forced split** — voice needs its own Gateway + UDP
  connection, so it runs as its own worker (its own voice connection), fed via
  the same dispatch seam. It **never** folds into the edge.
- The `DispatchPort` makes "in-process vs Lambda vs its-own-service" a **deploy
  detail**: peel a skill into its own service when it earns it, with no code
  change.

### 3. Hosting — the always-on holder

- **Holder:** a small always-on box runs the Gateway edge. **AWS Lightsail
  ($5/mo, flat, IPv4 bundled)** is the blessed choice; a DigitalOcean $4 droplet
  is an acceptable equal. Discord is IPv4-only, so any direct holder pays the
  unavoidable public-IPv4 cost; serverless cannot hold the socket.
- **Brain worker:** AWS Lambda (scale-to-zero), invoked by the edge's
  `DispatchPort`.
- **Homelab stays opaque.** If self-hosting compute later, homelab is a **private
  backend behind WireGuard** — Discord only ever sees the AWS holder's IP; the
  socket never moves home. Backends hot-swap (Lambda ↔ homelab) live via the
  dispatch seam; the holder is replaced only via Gateway RESUME.

### 4. LLM provider — agnostic, privacy-first default

- A provider-agnostic LLM client `Protocol` with adapters (OpenAI-compatible and
  AWS Bedrock Converse). No hard SDK dependency in the shared kernel.
- **Default: Gemma 4 (26B-A4B) on AWS Bedrock** — open-weight (Apache 2.0),
  native tool calling, in-boundary for privacy, ~cents–low-$/mo at this scale.
  **OpenRouter (free Gemma 4)** is the dev/low-volume adapter. The model is the
  same across both, so the provider is a config flip.

### 5. Repository structure — uv workspace, hexagonal

A uv workspace (one `uv.lock`, one venv, shared tool config at root). Group by
**role**, per the DDD Shared Kernel + ports-and-adapters split:

```
petbot/
  domain/          Shared Kernel (small): value objects, enums, PORT interfaces only.
                     SkillSpec, SkillResult, SkillContext, EmbedSpec, User,
                     Capability/Platform enums, DispatchPort/VoicePort/SessionStore ports.
  platform/        Infrastructure lib: entry-point plugin loader, manifest tooling,
                     DispatchPort/SessionStore ADAPTERS (in_process/lambda/sqs; memory/dynamo).
  frontends/       Driving adapters (one per platform).
    discord/         the Gateway edge.
    (telegram/ web/  later)
  skills/          Entry-point plugins (group "petbot.skills"); each its own deps.
    booru/ math/ music/ chat/   (chat = the LLM agent)
  deploy/          Deploy bundles (platform + a chosen skill set).
    edge/ core/ music/
```

- **`domain` is the Shared Kernel** — deliberately small: domain types +
  integration contracts (ports) only. *No* utilities, HTTP clients, or adapters
  (that would be a category error). Both frontends and skills depend on it;
  neither depends on the other.
- **Distribution names** `petbot-<role>-<name>` (`petbot-domain`,
  `petbot-platform`, `petbot-discord`, `petbot-skill-booru`). Skills import
  top-level (`petbot_skill_booru`) and register via **entry points**, so a broken
  plugin can't poison a shared namespace.

### 6. Capabilities — a requirement/provision duality, split by kind

The old single `Capabilities` flag-set (frontend-advertised, skill-branched) is
reorganised:

- **Hard requirements** (a skill cannot run without it: `VOICE`,
  `MESSAGE_CONTENT`) move onto **`SkillSpec.requires: frozenset[Capability]`**
  (generalising today's `requires={"voice"}`). The frontend declares
  **provisions**; the dispatcher exposes a skill iff `requires ⊆ provides`.
- **Runtime flags** (the skill still runs but *adapts*: `allows_explicit`/NSFW —
  booru works SFW *and* NSFW, NSFW only raises the rating floor) stay on
  **`SkillContext`** as per-request data the skill reads.

So hard reqs live with the skill (matched for exposure); soft/runtime facts live
on the context (read for behaviour).

### 7. Interactions removed

`petbot/frontends/interactions/` (the HTTP-Interactions Lambda adapter) is
**deleted**. It was a *second transport for Discord*, an artifact of ADR 0005's
serverless experiment; under the single-Gateway design, Discord has one frontend. Its
*generic-dispatch pattern* (route by name, no per-skill code) survives as the
edge's dispatch shape; the package does not.

## Relationship to prior ADRs

- **Supersedes ADR 0005's *ingress* decision** (HTTP-Interactions-on-Lambda as
  the blessed front door, gateway "parked"). **Keeps** 0005's compute seam — the
  `DispatchPort`/`RemoteSkill` idea is now the *primary* mechanism, not a
  music-only special case. The SQS bus survives for the music worker.
- **Realises ADR 0002** — the deferred LLM layer; the agent is a **skill**
  (`petbot-skill-chat`) that runs the tool-loop over the manifest and dispatches
  to other skills.
- **ADR 0003** (neutral core) stands — the dependency rule is preserved and
  sharpened into the `domain` Shared Kernel.

## Migration map (target ← current)

| Current | New home |
| --- | --- |
| `petbot/core/skills/{context,base,registry}.py` (types/contracts) | `domain/` (split: value objects, `SkillSpec`, ports) |
| `petbot/core/skills/ports.py` (`VoicePort`) + new `DispatchPort`/`SessionStore` | `domain/` ports |
| `petbot/core/skills/{math,booru,music}_skill.py` | `skills/{math,booru,music}/` |
| `petbot/core/capabilities/boorus/` | `skills/booru/` (its engine) |
| `petbot/frontends/discord/` (cogs → generic dispatch + `@mention`/presence) | `frontends/discord/` (reshaped; per-skill cogs deleted) |
| `petbot/frontends/interactions/` | **deleted** (§7) |
| dispatch/session adapters, plugin loader, manifest tooling | `platform/` |
| Lambda packaging, Terraform | `deploy/{core,edge,music}/` |
| (new) LLM agent + provider adapters | `skills/chat/` |

The migration lands in staged, reviewable commits: scaffold `domain` → extract
one skill end-to-end as the pattern → reshape the edge → port remaining skills →
delete `interactions` → deploy bundles → LLM agent.

## Consequences

- **One Discord ingress, one command surface.** The duplicate command
  implementations (cogs vs. interactions) collapse to one generic, manifest-driven
  path.
- **Minimal edge.** The holder carries no skill deps (no `httpx`/`numexpr`/
  `yt-dlp`); skills' dependencies live in their own packages/workers.
- **A new always-on cost** (~$5/mo holder) that ADR 0005 avoided — the price of
  conversational chat. Inference is ~cents–low-$/mo on Gemma 4.
- **Bigger restructure.** A uv-workspace, multi-package repo replaces the single
  package; CI, packaging, and import-linter contracts are rewritten around the new
  boundaries (frontends ↮ skills, both → `domain`; `domain` imports nothing).
- **Music keeps its bus.** `/music` stays decoupled (its own voice worker), so the
  `DispatchPort` + SQS seam from ADR 0005/#33 is retained, not removed.
- **Issues realign** to this design: #28 (topology), #39 (inverted — gateway is blessed),
  #31 (gateway mode, Message Content on, no endpoint URL), #33 (music worker
  retained), #35 (dispatch-deferred), #30/#42/#38 (Lambda → compute tier).

## References

- Builds on / supersedes: ADR 0005 (serverless deployment), ADR 0002 (deferred
  LLM), ADR 0003 (neutral core).
- Epics/issues: #15 (LLM), #28 (deploy), #8 (2.0).
