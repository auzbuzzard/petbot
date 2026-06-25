# ADR 0011: Agent observability (OpenTelemetry, metadata-only)

- Status: Accepted
- Date: 2026-06-22

## Context

An incident — PetBot silently not calling the `e621` skill when asked — was
**undiagnosable from the logs**. The core Lambda ran cleanly (no warning/error over two
days), because the failure was model *behaviour*: the agent either declined the tool or the
search came back empty, and **neither path logs anything**. PetBot recorded none of what
matters for an LLM agent: the model's tool-call decisions, token usage, latency, or a
correlation id tying a Discord complaint to a run. Worse, the Lambda configured no app
logging at all, so even INFO records never reached CloudWatch.

`pydantic-ai` (already at 1.x) ships first-class OpenTelemetry instrumentation following the
GenAI semantic conventions — agent-run → model-request → tool spans, with `gen_ai.usage.*`
token metrics — and it was entirely unused.

## Decision

- **Instrument with the OTel API everywhere, configure the SDK once per entrypoint.**
  `opentelemetry-api` is a base dependency and a no-op until a provider is installed; the SDK
  + OTLP exporter are wired by `configure_observability()` in
  [`petbot/observability.py`](../../src/petbot/observability.py), a sibling of
  `configure_logging` called by each entrypoint (Lambda handler, dev HTTP, Discord edge,
  music). This honours invariant 6 ("logging/telemetry configured once, at the entrypoint")
  and keeps the SDK out of import paths that don't need it.

- **The domain kernel is untouched.** Trace context is transport-plane metadata, so it rides
  the `petbot.platform` `Dispatch` wire (a `"trace"` carrier injected in `_wire`, extracted in
  `serve`) as **W3C tracecontext** — never `SkillContext`. `AwsXRayIdGenerator` makes the
  trace ids X-Ray-valid, so no AWS-specific propagator is needed (we never cross an
  `X-Amzn-Trace-Id` hop). One Discord turn is one trace: `dispatch` (edge) → `serve` (core) →
  `invoke_agent` → model/tool spans.

- **DI, not globals, for the agent.** The composition root builds an
  `InstrumentationSettings(version=3, include_content=False)` from the global providers and
  injects it into `ChatProcess` → `build_agent`; tests pass an in-memory provider.

- **Backend is AWS-native, collector-less.** Spans/metrics export over OTLP **straight to
  AWS's endpoints** — traces to the X-Ray OTLP endpoint, metrics to the CloudWatch
  (`monitoring`) OTLP endpoint — each POST SigV4-signed with the runtime's own credentials
  (the Lambda role for the core, the edge's scoped IAM key for the frontend). Nothing runs
  alongside the app — the worker image bakes in no extension and the edge has no sidecar. The wire
  is vendor-neutral OTLP, so a non-AWS `OTEL_*` endpoint (a plain collector in dev) is left
  unsigned and works as a drop-in. **Traces require CloudWatch Transaction Search** (metrics
  don't), which is two parts: a CloudWatch Logs resource policy letting X-Ray write to the
  `aws/spans` log group (managed in `observability.tf` when enabled) plus a one-time
  per-account/Region destination toggle that has no TF resource yet — `aws xray
  update-trace-segment-destination --destination CloudWatchLogs`. Until both, the X-Ray OTLP
  endpoint rejects spans.

- **Telemetry is metadata-only — privacy by construction.** `include_content=False` means
  pydantic-ai never records message bodies or tool arguments/results; there is nothing to
  scrub. The only identifier attached is a **salted hash** of the user id (`hash_user_id`).
  Two extra non-content signals recover the e621 case without content: a per-run **outcome
  log** (tool names, tokens, finish reason — the always-on CloudWatch path, emitted by
  `ChatProcess`) and a coarse **booru outcome** status (`ok | empty | safe_limited | error`)
  on the tool span. Off by default (`OBS_ENABLED`).

- **Per-guild consent was considered and rejected.** Because telemetry carries no message
  content and (for self-hosters) stays in the operator's own AWS account, no per-guild opt-in
  store or consent command is needed — data minimisation does the work that consent UX would.
  See `PRIVACY.md`.

## Consequences

- The next "did it call e621, and what came back?" is answerable from one trace + one log
  line; the outcome **log** is always-on (CloudWatch, off the Lambda's stdout), independent of
  whether the OTLP **export** is enabled, so it survives even with telemetry off entirely.
- New deployables (`observability` extra) ship the OTel SDK + botocore (to SigV4-sign the
  export); the edge exports directly too, so its previously ephemeral Lightsail logs are no
  longer the only record.
- The Lambda now configures logging at cold start (JSON in prod), closing the gap that hid
  every INFO record.
- A documented, minimal telemetry schema ([`docs/telemetry.md`](../telemetry.md)) states
  exactly what is collected — the open-source norm.
