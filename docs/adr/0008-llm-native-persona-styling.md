# ADR 0008: LLM-native persona — structured results and the slash Style port

- Status: Accepted (with a known limitation; see *Open issue*)
- Date: 2026-06-21
- Builds on the edge/worker split in [ADR 0006](0006-gateway-edge-microservice-skills.md)
  and the chat agent in [ADR 0007](0007-llm-agent-pydantic-ai.md).

## Context

PetBot's in-character copy lived in `booru/utterances.toml` — a static phrase bank
the model picked from at random. It could not adapt to a result, repeated itself,
and split the persona across a data file and the chat system prompt. We want to go
**LLM-native**: skills emit *facts*, and PetBot's voice is generated from a prompt.

The wrinkle is that there are two output paths:

- **@mention** runs the chat agent (ADR 0007); the agent already voices its reply.
- **slash** (`/derpi wolf`) dispatches a skill directly, with **no LLM in the loop**
  to add a voice.

So the persona has to be applied to the slash path *somewhere*, and only there.

## Decision

**Persona is prompt, not data.** Split package-data prompts: `persona.md` (the voice,
as described traits + a couple of exemplars — not a copy-list), `agent.md` (the chat
agent's tool-use / no-invented-reason rules), `stylizer.md` (a faithful one-line
rewrite). `utterances.toml` and the random greeter are deleted.

**Skills return modelled outcomes.** `booru/render` no longer ships greeter prose: a
found result is a card with no text; an empty result is an `EmptyReason`
(`safe_floor` / `no_match`) rendered once to a factual note. The voice is added
downstream.

**The slash persona is a port, mirroring music's voice.** `StylePort` /
`StyleProvider` are domain Protocols, shaped like `VoicePort` / `VoiceProvider`
(ADR 0006, invariant 4): the persona model is resolved **worker-side** and never
crosses the wire. The core worker holds an `LLMStyleProvider`; the dispatch boundary
(`Worker.run`) applies the port the provider returns. Nothing is added to the `Skills`
protocol, and the edge stays thin (it does not orchestrate a second call).

**The trigger is a per-request flag on the context.** `Worker.run` cannot tell a
direct slash `derpi` from a `derpi` the chat agent called as a tool — same skill,
same-shaped context. So the originating frontend signals intent:
`SkillContext.style_results` is set `True` by `build_interaction_context` (slash) and
left `False` by `build_context` (@mention); a nested chat tool-call reuses the agent's
context and inherits `False`. The provider's `for_context(ctx)` returns a port only
when the flag is set.

**Tiered models.** Optional `CHAT_STYLIZER__*` — the same `LLMConfig` discriminated
union as the agent — picks a cheaper model for the stylizer (e.g. Nova Micro). Unset
reuses the agent's model.

## Consequences

- One source of voice (the prompt); the persona adapts per result instead of parroting.
- The edge gains nothing: no styling logic, no second dispatch, no LLM dependency.
- A cheaper stylizer tier is a config flip, not code.
- Token cost is negligible at this scale (the always-on edge holder dominates), so the
  tier is chosen for latency/fit, not savings.

## Open issue — the pipeline does not yet match the intended DDD layering

The trigger above is the cheapest option *within the current pipeline*, and shipping
it surfaced a deeper concern the maintainer has flagged: **the request → dispatch →
result pipeline entangles presentation with the domain in a way that does not match
the intended DDD layering.** A fuller refactor is expected; this ADR will be revisited
(likely superseded) then. The reasoning that led to the discovery is recorded here, so
the refactor starts from it rather than re-deriving it.

### How the discovery surfaced

The objects involved sit in different layers:

- **`SkillContext`** is a domain value object — the neutral *facts about a request*
  (user, conversation, `allows_explicit`). It is serialised across the wire and handed
  to **every** skill's `run(args, ctx)`. Skills *read* it.
- **`SkillCall`** is the dispatch envelope (`skill` + `args` + `context`). The worker
  unpacks it; the skill never sees it. It is routing, not request-facts.
- **`Worker.run`** is the generic application-layer dispatcher: name → skill → result.

Styling has to happen on the slash path and *only* there, because the worker cannot
distinguish a direct slash `derpi` from a `derpi` the chat agent invoked as a tool —
same skill, same-shaped context, same `Worker.run`. So a per-request signal must ride
along. We put it on `SkillContext` (`style_results`).

### Why that is a layering problem, not just a placement choice

Following the data flow makes the smell visible:

- `style_results` is a **presentation / delivery directive** ("voice this answer")
  living inside a **domain value object** that otherwise describes *what the request
  is*. The domain model now mixes "what" with "how to deliver", and a skill could
  branch on a flag that was never meant for it.
- `Worker.run` — the generic dispatcher — now **executes a presentation transform**
  (it calls a styling port). A concern that belongs at/above the frontend boundary has
  been pushed *down* into the application core.

The trigger only has to exist *because the responsibility for voicing was placed in the
wrong layer*. If presentation/voicing lived where presentation belongs (a per-frontend
presentation boundary — the edge already renders results; the @mention path already
voices via the agent), neither the domain context nor the generic dispatcher would need
to carry or interpret a styling flag at all. Options A/B/C below all move the *flag*
around inside the same frame; the real question the refactor must answer is **which
layer owns turning a neutral `SkillResult` into a voiced one, per frontend** — i.e. the
frame itself, not the flag.

### Placements considered (all within the current frame)

- **A — flag on `SkillContext` (chosen).** Lowest friction: the context is already
  threaded through `skills.derpi(args, ctx)`, and nested calls inherit it for free.
  Cost: the layering smell above.
- **B — field on the `SkillCall` dispatch envelope.** More honest as a dispatch
  directive (invisible to skills), but `SkillsClient` builds `SkillCall` internally and
  the edge only calls `skills.derpi(args, ctx)`; threading a flag needs `Skills`-API and
  wire-envelope surgery.
- **C — carry the frontend's `Capability` set on the context and *derive* styling.**
  Most aligned with the existing model (`MESSAGE_CONTENT` already hints at the
  conversational-vs-slash distinction), but introduces frontend-capabilities-on-context.

<!-- TODO(maintainer): record the target layering for presentation/voicing (where a
neutral SkillResult becomes a voiced one, per frontend) when the refactor is scoped. -->

