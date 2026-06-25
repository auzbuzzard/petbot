# Telemetry schema

The exhaustive list of what PetBot emits when telemetry is enabled (`OBS_ENABLED=true`).
**No message content is ever recorded** — no prompts, replies, or search tags. See
[ADR 0011](adr/0011-agent-observability.md) and [`PRIVACY.md`](../PRIVACY.md). Disabled by
default; everything below is a no-op until an operator opts in.

## Traces (OTLP → AWS X-Ray)

One trace per Discord turn. Span tree:

```
dispatch (edge)                 # petbot.frontends → petbot.platform.client
└─ serve (core)                 # petbot.platform.serve
   └─ invoke_agent agent        # pydantic-ai
      ├─ chat <model>           # pydantic-ai model request
      └─ execute_tool <name>    # pydantic-ai tool call (e.g. e621)
```

Attributes we set (beyond pydantic-ai's GenAI-semconv span data, which carries
`include_content=False`, so **no** `gen_ai.*.messages` content):

| Attribute | Spans | Example | Notes |
|---|---|---|---|
| `petbot.platform` | dispatch, serve | `discord` | originating frontend |
| `petbot.conversation_id` | dispatch, serve | `discord:123` | channel/room id, not a person |
| `petbot.input_kind` | dispatch | `TextInput` | class name only |
| `petbot.booru.outcome` | tool span | `safe_limited` | `ok \| empty \| safe_limited \| error` |
| `gen_ai.usage.input_tokens` / `output_tokens` | model/agent | `412` / `28` | from pydantic-ai |
| `gen_ai.response.finish_reasons` | model | `["stop"]` | from pydantic-ai |

## Metrics (OTLP → CloudWatch)

| Metric | Type | Attributes | Meaning |
|---|---|---|---|
| `petbot.agent.tool_calls` | counter | `tool` | tool calls, by tool name |
| `petbot.agent.zero_tool_runs` | counter | — | agent runs that called no tool (the e621-style alarm) |
| `petbot.agent.lost_context_runs` | counter | — | runs answered with an unreadable reply context |
| `petbot.booru.outcome` | counter | `provider`, `status` | searches by provider + outcome |
| `gen_ai.client.token.usage` (and peers) | histogram | from pydantic-ai | token usage per request |

## Logs (structured JSON → CloudWatch Logs)

One `agent run` record per chat turn (`petbot.process.chat`, level INFO):

| Field | Example | Notes |
|---|---|---|
| `tools` | `["e621"]` | tool names called |
| `tool_count` | `1` | |
| `input_tokens` / `output_tokens` | `412` / `28` | |
| `requests` | `2` | model requests in the run |
| `finish_reason` | `stop` | |
| `model` | `gemma-4-...` | |
| `output_len` | `44` | reply length (a count, not text) |
| `context` | `recalled` | reply chain was read, or `unrecalled` if it couldn't be |
| `user` | `6ac78c04e065ba99` | **salted SHA-256 hash** of the Discord user id (16 hex) |

No field above contains message text, tags, the raw user id, or a display name.
