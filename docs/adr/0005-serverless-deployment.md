# ADR 0005: Serverless deployment — HTTP-Interactions core on AWS Lambda, gateway skills as remote workers

- Status: Accepted
- Date: 2026-06-04

## Context

PetBot needs a live deployment on a dev guild (dev) and the main server
(prod + UAT). The existing runtime is a **discord.py gateway bot** — a
persistent process holding a WebSocket to Discord's Gateway, plus FFmpeg/yt-dlp
for voice. That shape forces a 24/7 process and (if self-hosted) inbound
exposure.

But Discord offers a second, stateless way in: **HTTP Interactions**, where
Discord POSTs each slash command to a URL. Everything PetBot does today except
`/music` is request/response and fits that model. `/music` is the lone
exception — voice fundamentally requires a Gateway connection plus a live voice
(UDP) stream, which cannot be serverless.

Hosting was evaluated (June 2026):

- **Cloudflare Workers (Python)** — viable now (`httpx` works via the Fetch
  shim), but still beta, has **no outbound WebSocket/UDP** (so voice can never
  run there), and `numexpr` (a C-extension) is not in Pyodide.
- **AWS Lambda** — runs the existing Python skills unchanged (`numexpr`
  included), GA, generous permanent free tier.
- The serverless front door is **~$0** at PetBot's scale on Workers, Lambda, and
  DO Functions alike; the only real cost is an always-on host, which only
  `/music` needs.

The neutral core (ADR 0003) already separates skills from transport and gates
them on `Capabilities`/`requires`, so a second frontend is additive.

## Decision

Deploy PetBot as **independently deployable transport adapters over the one
neutral core**, split by what each skill needs:

- **Stateless skills** (`/ping /math /derpi /e621 /purge`) run behind a new
  **HTTP-Interactions adapter** (`petbot/frontends/interactions/`) on **AWS
  Lambda** (Function URL). It verifies Discord's Ed25519 signature, maps the
  interaction → `SkillContext`, and renders `SkillResult`/`EmbedSpec` to raw
  interaction-response JSON (no `discord.py`). Infra is **Terraform**, in-repo.
- **Gateway-required skills** (`/music`, and the future LLM chat layer of ADR
  0002) run as a **persistent worker image** (the existing
  `petbot/frontends/discord/` adapter) on the homelab cluster.
- **Topology is "Option C": one Discord application.** All slash commands go to
  the HTTP endpoint. Setting an Interactions Endpoint URL diverts *all*
  interactions off the Gateway, so the split cannot be per-command within one
  app — the music worker therefore does **not** receive the slash command. It
  holds a Gateway connection purely for voice and is driven out-of-band.
- **The Lambda is agnostic to where a skill runs.** A remote skill is a
  **proxy** implementing the same `Skill` interface: its `run()` enqueues a job
  on a message bus and returns a deferred ack; the worker **consumes** the
  queue, runs the real skill, and posts the result back via the interaction
  follow-up token (or a bot-REST message). A neutral `DispatchPort` (mirroring
  `VoicePort`) keeps the bus client out of the core.
- **The worker pulls from the queue**, so there is **no inbound exposure** to
  home and no tunnel — voice is outbound-only.
- **Deploy is two pipelines, not one orchestrator:** `terraform`/`wrangler`-style
  push for the serverless unit; **GitOps pull** (Argo CD/Flux in-cluster) for
  the worker image. They share only the repo, the bus contract, and the Discord
  app config.
- **`/music` is deferred** for the first cut. The initial deployable is a
  **single Lambda** with the stateless skills; the music proxy/worker/bus are
  designed for but not built. Because the interactions adapter declares
  `supports_voice=False`, the registry already hides `music` — no special-casing.

## Consequences

- 5 of 6 commands need **no 24/7 process and no inbound home exposure**, at ~$0.
- Re-activating `/music` is purely additive (a `RemoteMusicSkill` proxy + the
  worker image + an SQS queue) with **no change** to the other skills — and the
  same seam enables arbitrary hybrid placement (some skills local, some on
  Lambda) and the future LLM gateway worker.
- A new cost: the front-door → worker **message bus** is the one extra moving
  part, and its job schema becomes a cross-version compatibility contract (moot
  while music is deferred).
- `numexpr` stays on Lambda. Swapping `/math` to a pure-Python evaluator is
  **optional**, needed only to keep Cloudflare Workers open as an alternative
  host.
- The interactions adapter must stay `discord`-free (raw JSON rendering) so it
  runs on minimal runtimes; enforced by the same `import-linter` /
  `test_core_isolation` discipline as the core.
- Whether the endpoint uses a custom `auzbuzzard.net` hostname (vs. the raw
  Lambda Function URL) is left open — Lambda Function URLs don't natively take
  custom domains, so it needs deliberate plumbing. Tracked separately.

## References

- Tracking: epic #28; sub-issues #29 (adapter), #30 (Terraform), #31 (Discord),
  #32 (domain), #14 (smoke test), #33 (music remote skill), #17 (secrets/ops).
- Builds on ADR 0003 (neutral core) and intersects ADR 0002 (the deferred LLM
  layer lives in the gateway worker, not Lambda).
