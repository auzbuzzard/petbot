# ADR 0013: LeetCode skill — direct GraphQL, no client library

- Status: Proposed
- Date: 2026-10-22
- Builds on the skill recipe in [ADR 0006](0006-gateway-edge-microservice-skills.md)
  and skills-as-agent-tools in [ADR 0007](0007-llm-agent-pydantic-ai.md).

## Context

PetBot cannot answer "what's today's LeetCode daily?" — the case captured by
[`conversations/leetcode-daily.json`](../../conversations/leetcode-daily.json), where a user
asks for the daily and, when the bot guesses, insists it "actually look it up." The two web
tools can't close this: the daily is dynamic data behind LeetCode's GraphQL endpoint, so
`web_search` returns stale blog/forum posts, and `web_fetch` of `leetcode.com` gets a
JavaScript app shell with no problem content to extract.

The three Python LeetCode libraries checked (from their READMEs and PyPI pages, not their
code) fit none of the skill constraints (async `httpx`, `mypy --strict`, minimal
dependencies, no event-loop blocking, no auth):

- `python-leetcode` (no release date found) requires a logged-in session
  (`LEETCODE_SESSION` + CSRF cookies) and documents no daily helper — auth-gating alone
  rules it out for a public lookup. Its examples are synchronous.
- `leetscrape`, last released early 2024, scrapes problem pages rather than the daily. Its
  examples are synchronous and suggest a pandas DataFrame workflow; its PyPI page lists no
  dependencies, so that is inferred.
- `leetcode-api-wrapper` lists a daily call, but wraps a third-party **hosted proxy**,
  coupling us to someone else's free instance to wrap a single HTTP call. (Its PyPI page
  didn't load, so its sync/async API is unconfirmed.)

The open-source bots sampled for this decision (a handful, not a survey) each fetch the
daily with one unauthenticated GraphQL request; a library would add a dependency, often an
auth or proxy requirement, and likely a blocking call to wrap `httpx.post`.

The open risk was reach: LeetCode sits behind Cloudflare, and one third-party writeup
reported cloud/datacenter IPs being bot-blocked, which would matter because the core runs on
Lambda. We spiked it before deciding (see Spike evidence).

## Decision

Add a dedicated `leetcode` skill rather than lean on the web tools, following the ADR 0006
recipe (args model in `petbot.types`, a `CATALOG` entry, a `Skill` under
`petbot.skills.leetcode`).

- **No client library — call the endpoint directly** with PetBot's own `httpx` client,
  unauthenticated. Two operations:
  - the daily (`activeDailyCodingChallengeQuestion`), and
  - a random problem, drawn from the difficulty-filtered problem list.
- **The skill stays two thin data operations; the agent does the reasoning.** The
  fixture's conditional ("is today's daily an easy? if so pick it, else pick another easy
  one") is resolved by the agent calling the tool — daily first, then random-by-difficulty —
  not by branching logic baked into the skill. So the daily operation exposes the problem's
  difficulty as structured data, and random-by-difficulty exists as its own path.
- **Arguments** are an optional `mode` (`daily` | `random`) and an optional `difficulty`
  (`easy` | `medium` | `hard`, only meaningful for `random`). With no `mode`, a given
  difficulty means `random`, so asking for "an easy one" never returns the daily.
- **A fallback provider is deferred, but the seam is not.** The skill is written as a
  ranked-provider chain like `web_search` (primary first, fall through on failure), so a
  hosted unofficial API can be slotted in **if** the direct call is later observed to fail
  from the deployed runtime. We do not ship a second provider now, because the spike did not
  reproduce a block — adding one speculatively would mean a standing dependency on a
  third-party instance we don't need.
- **Unauthenticated only.** No account features (streaks, "did I solve it", submissions) —
  those need session cookies and are out of scope.
- **Surfaced on both paths.** The skill returns a finished answer, so it is a slash command
  as well as an agent tool (`slash=True`), unlike the web tools.
- **Tests mock the GraphQL responses** (invariant 7); the query shape is community-derived
  and pinned in our own code, so a schema change is caught by the tests, and the
  `conversations/leetcode-daily.json` fixture is the live-model acceptance check via the chat
  harness.

## Spike evidence

Labelled by source class, because the result turns on where the request originates:

- **Verified** (local run, 2026-10-22, residential IP via Cloudflare's SJC edge): the direct
  unauthenticated POST returns HTTP 200 with the expected JSON for both the daily and the
  difficulty-filtered list. A bare `Content-Type: application/json` was enough — no browser
  User-Agent, Referer, or Origin was needed — and no Cloudflare challenge was served.
- **Inference / unverified**: the request was **not** exercised from the Lambda runtime's
  own datacenter IP. A plain GET from a cloud IP reached LeetCode's origin (an app-level
  400, not a Cloudflare challenge), which shows reachability but not that a POST passes
  unchallenged from that range. The Lambda-origin case therefore remains unverified.
- **Single report**: one third-party writeup reported Cloudflare blocking cloud bots. It was
  not reproduced here, but it is the reason the fallback seam is kept.

## Consequences

- The happy path is dependency-free: one new skill, no new runtime package, built from the
  existing skill recipe plus one `CATALOG` entry.
- The daily case becomes answerable with real, dated data instead of a guess; the
  `leetcode-daily.json` fixture should pass against the live model.
- Schema drift (the query is community-derived, not an official contract) is the standing
  risk, bounded by the mocked tests and the fallback seam.
- If the direct call is observed failing from the deployed runtime, the fix is to implement
  the deferred fallback provider behind the seam — not to re-architect the skill.
- Account-scoped features stay out until there is a reason to take on authenticated,
  per-user state.
