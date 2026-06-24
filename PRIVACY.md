# PetBot Privacy Policy

_Last updated: 2026-06-22_

> **Operators:** before publishing a hosted instance, replace every **[BRACKETED]**
> placeholder below (controller name, contact email, jurisdiction). If you self-host, see
> [Self-hosting](#self-hosting) — you become the data controller and this document is your
> template.

This policy describes how the hosted **PetBot** Discord bot ("PetBot", "we", "us") handles
information. It is written to satisfy Discord's Developer Policy (a publicly accessible
privacy policy is required for the Message Content intent) and the EU GDPR.

## Who we are (data controller)

The data controller for the hosted instance is **[CONTROLLER NAME]**, contactable at
**[CONTACT EMAIL]**. The controller is established in **[JURISDICTION]**.

## What PetBot processes, and why

PetBot replies when you @mention it or reply to one of its messages.

- **Message content (processed, not stored).** To generate a reply, PetBot reads the text of
  the message that mentions or replies to it, plus the immediate reply-chain it is part of.
  This content is used **in memory to produce the response and then discarded**. We do **not**
  write message content to any database, log, or telemetry system.
- **Search queries.** A message may ask PetBot to search an image board (Derpibooru, e621).
  The query is sent to that third-party site to fetch a result. The query text is **not**
  stored by us.

We rely on **Discord's privileged Message Content intent** to receive this text; its use is
limited to producing replies, as described above.

## What PetBot collects (telemetry)

PetBot emits **operational telemetry only — never message content.** Specifically:

- model and token counts, request/response latency, and which tools (skills) a request
  called and their coarse outcome (e.g. a search returned `ok` / `empty` / `safe_limited` /
  `error`);
- a **salted one-way hash** of the requesting user's Discord id (so we can correlate one
  user's requests for debugging) — never the raw id, username, or display name;
- the channel/conversation id (a room identifier, not a person).

No prompts, replies, search tags, or any message text are collected. The complete, exhaustive
list of fields is documented in [`docs/telemetry.md`](docs/telemetry.md). Telemetry can be
disabled entirely by the operator (`OBS_ENABLED=false`).

## Lawful basis

Telemetry is processed under **GDPR Article 6(1)(f) (legitimate interests)** — keeping the
service reliable and debuggable — applying data minimisation (metadata only, identifiers
pseudonymised). Message content is processed under the same basis solely to deliver the reply
you asked for, and is not retained.

## Sub-processors and storage

Telemetry is sent to **Amazon Web Services** (AWS X-Ray for traces, Amazon CloudWatch for
metrics and logs) in the controller's own AWS account, region **[AWS REGION]**. Model
inference is performed by **[MODEL PROVIDER]** to generate replies. We use no other
sub-processors and do not sell or share data for advertising.

## Retention

- Message content: **not retained** (processed in memory, then discarded).
- Traces (X-Ray): **30 days**.
- Metrics / logs (CloudWatch): per the operator's configured retention (default 30 days).

## Your rights

Subject to applicable law, you may request access to, or erasure of, personal data we hold
about you. Because we store no message content and only a salted hash of your user id, the
data we can act on is limited; contact **[CONTACT EMAIL]** and include your Discord user id.

## Children

PetBot is not directed to children under the age required by Discord's Terms of Service.

## Changes

We may update this policy; the "Last updated" date reflects the latest version. Material
changes will be noted in the project's release notes.

## Self-hosting

PetBot is open source (Apache-2.0). If you run your own instance, **you** are the data
controller for it: telemetry stays in **your** AWS account and never reaches the project
authors. You are responsible for your own privacy policy and for honouring the obligations
above for your users. Telemetry is **off by default** (`OBS_ENABLED` unset); enabling it is
your decision.
