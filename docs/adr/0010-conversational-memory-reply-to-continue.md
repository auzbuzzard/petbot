# ADR 0010: Conversational memory — reply-to-continue, reactive context handling

- Status: Accepted
- Date: 2026-06-22
- Builds on the process pipeline ([ADR 0009](0009-process-pipeline.md)) and the chat
  agent ([ADR 0007](0007-llm-agent-pydantic-ai.md)).

## Context

Chat was stateless single-shot: an `@mention` built `TextInput(text=…)` and the agent
ran with **no `message_history`**, so replying to PetBot did nothing — the compute
service only ever saw the latest message. Users expect to reply to PetBot and have it
continue the conversation.

Two facts shaped the design:

1. The compute service is a **stateless Lambda** (ADR 0006/0009) — it can't hold
   conversation state between requests.
2. The frontend holds the gateway, so it is the **only** component that can read a
   message's reply chain (`message.reference`).

## Decision

### Memory — reply-to-continue, reconstructed frontend-side (Route A)

- A reply to one of PetBot's own messages continues the conversation, with **no
  re-@mention** needed. `frontends/discord/history.py` walks `message.reference`
  ancestors (bounded by `HISTORY_MAX_TURNS`, default 25 — a Discord-API cost bound, not
  a model-context bound) and maps them to neutral `Turn` values.
- History rides on **`TextInput.history`** — the conversational variant of the `Input`
  sum type, so a `CommandInput` can't carry it. *Not* on the shared `SkillContext` (that
  would reintroduce the cross-path baggage ADR 0009 removed) and *not* a compute-side
  store (which can't see Discord's reply chain). The core stays a pure function of
  `(Input, SkillContext)`.
- `history` is itself a discriminated union — **`Recalled` | `Unrecalled`** — *not* a bare
  `tuple[Turn, …]`. When the frontend can't read the reply chain (e.g. a missing Discord
  *Read Message History* permission), the walk **raises** and the boundary degrades to
  `Unrecalled()`, distinct from an empty `Recalled()` (a genuinely fresh turn). This keeps
  "empty because fresh" and "empty because unreadable" from collapsing to the same value
  (no flag/boolean branching — ADR 0009 invariant). `ChatProcess.respond` exhaustively
  `match`es it: `Recalled` maps its turns to `message_history`; `Unrecalled` runs with no
  history **plus a per-run instruction** telling the agent it lost the thread, so it asks
  for a recap instead of answering blind.
- `Role` is neutral `USER`/`ASSISTANT`; the speaker's name (including "PetBot") lives on
  `Turn.author`, taken live from the Discord `display_name`. A user turn inlines its
  author for multi-user attribution; an image-only bot card is **flattened to a faithful
  text description** (its real title + image URL), since an assistant turn can only be
  text in the model's history.
- PetBot answers as a Discord reply (`mention_author=False`) so each answer is an anchor
  to continue from.

### Context window — reactive, no magic number

- pydantic-ai does **not** expose a model's context-window *size*
  ([#4538](https://redirect.github.com/pydantic/pydantic-ai/issues/4538)) and has no
  turnkey compaction
  ([#4137](https://redirect.github.com/pydantic/pydantic-ai/issues/4137)). A configured
  token budget would be a magic number that is wrong the moment the model is swapped
  (the provider config is built to be swapped).
- So compaction is **reactive**: the chat process attempts the run, and only if the
  provider rejects it for length (`is_context_overflow` — a best-effort `ModelHTTPError`
  match) does it compact the message history and retry, bounded by
  `MAX_COMPACTION_RETRIES`. The model's *real* window is the trigger; no budget is
  invented.
- The strategy is **DI-selectable** via `CHAT_CONTEXT__KIND` (a config `match`, like
  `build_model_from_config`): a zero-cost **sliding window** (drop the oldest half) or an
  **LLM summarizer** (a small stylizer-tier model summarises the oldest half).
  `to_model_messages` stays a pure neutral→model mapper; the window strategy is separate.

When the window size is exposed upstream, proactive precise budgeting can drop in behind
the same seam.

## Consequences

- **Zero new infrastructure**; the Lambda stays a pure function, and no conversation
  content lives at rest beyond Discord.
- Memory is **Discord-shaped** — a second frontend would reconstruct its own way (or
  motivate a compute-side store, deferred).
- The compaction trigger depends on recognising a provider's length rejection, which is
  provider-specific and best-effort: a false negative just skips the retry; a false
  positive costs one needless compaction.

## References

- Builds on ADR 0009 (process pipeline), ADR 0007 (the chat agent), ADR 0006
  (frontend/compute split).
- Upstream gaps, linked without cross-referencing (the `redirect.github.com` host form,
  as dependabot/Renovate use): pydantic-ai
  [#4538](https://redirect.github.com/pydantic/pydantic-ai/issues/4538) (expose the
  context-window size) and
  [#4137](https://redirect.github.com/pydantic/pydantic-ai/issues/4137) (first-class
  context compaction).
