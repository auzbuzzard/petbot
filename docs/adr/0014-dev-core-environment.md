# ADR 0014: A dev core: any branch's engine, deployed alone, on the production model with no key

- Status: Proposed (the SigV4 call to mantle is unverified until the spike below runs)
- Date: 2026-10-23

## Context

The chat harness (`python -m petbot.services.core.chat`) runs a branch's core in-process
against the real model, so a prompt or tool change can be read before it merges. It can't
show what only the deployed function does: whether a site answers requests from AWS's
addresses (ADR 0013's open question: does LeetCode's Cloudflare serve the Lambda?),
whether the function's IAM, packaging and time budget hold. The only deployed core was
production, and `deploy.yml` deployed only `main`.

What a pre-merge deploy needs, and what it must not bring:

- **The engine only.** The core and the endpoint providers (the Discord edge) are separate
  deployables. A dev core is exercised through the harness; a dev Discord bot, a second
  edge or a second Lightsail service are out of scope.
- **The production model.** `google.gemma-4-31b`, served only on Bedrock's
  OpenAI-compatible `bedrock-mantle` endpoint. Production authenticates with a Bedrock API
  key, minted by hand outside Terraform and stored in SSM.
- **Infrastructure as code, no hand-made credentials.** The dev environment, its CI role
  and its model access are Terraform, and a deploy role reachable from an unmerged branch
  must reach nothing of production's.

## Decision

### Model access: SigV4 with the function's own role (`chat_llm_kind = "bedrock_mantle"`)

AWS's endpoint table lists both Bedrock API keys and AWS credentials (SigV4) for
`bedrock-mantle` (documented: Bedrock user guide, *Chat Completions API*). A new provider
kind, `BedrockMantleModel` (`kind = "bedrock_mantle"`: model + base URL, no key), hands
pydantic-ai's OpenAI provider an `httpx` client whose `SigV4Auth`
(`petbot.process.sigv4`) signs each request for service `bedrock-mantle` in the Region
named by the endpoint's host, with botocore's default credential chain: the Lambda's role
in AWS, the developer's profile locally. The signing name is `bedrock-mantle` (documented:
the OpenAI Node SDK's Bedrock guide signs mantle requests for it; also the IAM service
prefix). Only `Content-Type` and `Host` are signed besides AWS's own headers, so headers
the transport adds after signing can't break it.

The function's role gets `bedrock-mantle:CreateInference` on
`arn:aws:bedrock-mantle:<region>:<account>:project/*` (documented: IAM service
authorization reference; `CreateInference` requires the `project` resource type), and
the environment's workload boundary allows the same. No key exists to mint, store, rotate
or leak, and nothing secret reaches Terraform state. `bedrock-mantle:CallWithBearerToken`
gates bearer-token calls (documented: IAM reference), so the role isn't granted it (inference:
a SigV4 call is not a bearer-token call; a third-party guide says the same).

Offline, unit tests recompute the signature by the published SigV4 algorithm (not by
botocore) over the request as it left the client, and drive a full chat turn through
pydantic-ai to a mocked mantle. **Whether mantle accepts the signed request for this model
is not yet observed**; the spike is a local harness run with the user's credentials
(README *Dev core*). If it fails, the fallback is a Terraform-managed Bedrock API key
(`aws_iam_service_specific_credential`), whose secret would land in Terraform state,
against `secrets.tf`'s rule that no secret value does; that trade-off is the user's to
make, not this ADR's.

### The dev stack: the root stack with `edge_enabled = false`, under `petbot-dev`

The root stack's edge resources (Lightsail service and deployment, edge ECR repo and
policy, edge IAM user, key and policies, claims table) are counted on
`var.edge_enabled`; `moved` blocks map production's existing unindexed addresses to
instance `[0]`, so production's state stays in place. A dev apply creates the core's ECR
repo, role, log group and Lambda (`petbot-dev-core`) and nothing else. A mock-provider
`terraform test` plans both shapes in CI.

### Bootstrap: one root of trust, an environment map

`bootstrap/`'s `var.environments` lists each deploy environment (`name_prefix`, GitHub
environment, and whether it runs the edge, sets a budget, calls mantle). Each gets its own
deploy role trusting only its GitHub environment, its own workload boundary and a deploy
policy scoped to its own `<name_prefix>-*` resources, `<name_prefix>/` state and
`/<name_prefix>/*` parameters; the edge's IAM-user and Lightsail rights, and Budgets, only
where they apply. One bootstrap manages both, so the account-global GitHub OIDC provider
stays one resource with no toggle. Production's role keeps its name
(`petbot-github-deploy`); dev's is `petbot-github-deploy-dev`, inside
`petbot-github-*`, which every deploy role is denied and bootstrap's pipeline manages.
`moved` blocks keep production's role, policy and boundary in place; rendered offline
against the previous code with fake credentials, production's trust, deploy permissions,
boundary and the pipeline roles' policies are identical. The operator may additionally
invoke `petbot-dev-core`.

The `dev` GitHub environment admits **every branch**: deploying an unmerged branch is the
point. Its role is the control: `petbot-dev-*` matches no production resource, and it
has no Lightsail (whose GUID ARNs can't be name-scoped), IAM-user or Budgets rights.

**Prefix.** `petbot-dev` sits inside production's `petbot-*` scope: production's deploy
role could manage dev resources, and production's workload boundary would admit a grant on
them; dev can reach nothing of production's. A prefix outside `petbot-*` would isolate both ways (the
bootstrap code supports one: the operator's scopes and the pipeline's policy list name it
explicitly). `petbot-dev` is the default because the exposed direction is the one `main`
and a required reviewer already guard; the choice is open to the user before merge.

### Deploy: `deploy.yml`'s `environment` input

A manual run picks `production` (default) or `dev`; a push to `main` always deploys
production. The environment sets the job's GitHub environment (so its role and variables),
the prefix, the state key `<prefix>/terraform.tfstate` and whether the edge is built.
Production's values are unchanged: `petbot`, `petbot/terraform.tfstate`, the same targeted
apply and the edge build. Runs take turns per environment.

### Talking to it: the harness's `--lambda`

`python -m petbot.services.core.chat --lambda petbot-dev-core <conversation>` sends the
same conversation through `ProcessClient` + `LambdaTransport`, the frontend's own path; a
failed dispatch gets the frontend's fallback reply. In-process remains the default.

## Consequences

- An unmerged branch is deployable and testable against production's model before merge,
  with no Discord, no edge and no secret.
- Production can move to `bedrock_mantle` later (its boundary needs `bedrock_mantle =
  true`), retiring the hand-minted key; not done here.
- Dev is one slot: each deploy replaces the last.
- Anyone who can push a branch can run code with the dev role and the dev core's role.
  Their reach is dev's resources and the model (cost: inference tokens).
- GitHub's environment settings (`dev`'s branch rule, its `DEPLOY_ROLE_ARN` secret and
  model variables) are set by hand, as for the existing environments.
