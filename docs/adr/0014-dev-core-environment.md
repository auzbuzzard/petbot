# ADR 0014: Two stages, prod and dev: any branch's engine on the production model, with no key

- Status: Proposed (production's migration, below, is not applied)
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

### Model access: SigV4 with the caller's own identity (`chat_llm_kind = "bedrock_mantle"`)

AWS's endpoint table lists both Bedrock API keys and AWS credentials (SigV4) for
`bedrock-mantle` (documented: Bedrock user guide, *Chat Completions API*). A provider kind,
`BedrockMantleModel` (`kind = "bedrock_mantle"`: model + base URL, no key), hands
pydantic-ai's OpenAI provider an `httpx` client whose `SigV4Auth`
(`petbot.process.sigv4`) signs each request for service `bedrock-mantle` in the Region
named by the endpoint's host, with botocore's default credential chain: the Lambda's role
in AWS, the developer's profile locally. The signing name is `bedrock-mantle` (documented:
the OpenAI Node SDK's Bedrock guide; also the IAM service prefix). Only `Content-Type` and
`Host` are signed besides AWS's own headers, so headers the transport adds after signing
can't break it.

The function's role gets `bedrock-mantle:CreateInference` on
`arn:aws:bedrock-mantle:<region>:<account>:project/*` (documented: IAM service
authorization reference; `CreateInference` requires the `project` resource type), and
the environment's workload boundary allows the same. `bedrock-mantle:CallWithBearerToken`
gates bearer-token calls (documented: IAM reference), so the role isn't granted it
(inference: a SigV4 call is not a bearer-token call). No key exists to mint, store,
rotate or leak, and nothing secret reaches Terraform state.

Verified: unit tests recompute the signature by the published SigV4 algorithm over the
request as sent; and a live in-process harness run of the LeetCode branch against
`google.gemma-4-31b`, signed with the developer's default AWS profile, got correct chat and
slash replies (reported by the session that ran it). Not yet observed: a call signed with
a Lambda role, i.e. the role policy and boundary above; the first dev deploy shows it.

### Stages: `petbot-prod` and `petbot-dev`, neither containing the other

Each stage's resources are named `<name_prefix>-*`: production `petbot-prod`, dev
`petbot-dev`. Neither prefix contains the other, so each stage's deploy role, workload
boundary, state (`<name_prefix>/`) and parameters (`/<name_prefix>/*`) cover its own stage
and nothing of the other's, in both directions. Bootstrap rejects an environment whose
prefix contains another's. Rejected: `petbot` and `petbot-dev` (production's `petbot-*`
covers dev); a non-overlapping but asymmetric `dev-petbot`. The root of trust is not a
stage and keeps its names: the CI roles (`petbot-github-*`), the operator
(`petbot-operator`), the OIDC provider and the state bucket.

The root stack's edge (Lightsail service and deployment, edge ECR repo, edge IAM user, key
and policies, claims table) is counted on `var.edge_enabled`, and `var.edge_paused`
disables its Lightsail service in place (its containers shut down: documented, Lightsail
API). A dev apply creates the core's ECR repo, role, log group and Lambda
(`petbot-dev-core`) and nothing else. The edge's Discord-token parameter defaults to
`/<name_prefix>/edge/discord_token`.

### Every setting is code: `stages/<stage>.tfvars`

Infrastructure changes only by merging code and running the repository's pipelines; no
one creates or edits a resource or a setting by hand. Each stage's deploy settings (model,
endpoint, whether the edge runs, its parameters) are a reviewed file,
`deploy/terraform/stages/<stage>.tfvars`, which `deploy.yml` passes to every Terraform
command; the pipeline reads no GitHub variable but the repository's `AWS_REGION`.

A secret the stack needs but can't mint is a parameter the stack owns
(`var.ssm_parameters`, `parameters.tf`), created with the value of an existing one: read
through an ephemeral resource and written with the write-only `value_wo`, so it reaches
neither the plan nor the state.

The only value the pipelines take from GitHub's settings is the AWS account ID, which the
public code leaves out: each deploy role's name is code, and `.github/scripts/deploy-role.sh`
builds its ARN with the account ID from the environment's `DEPLOY_ROLE_ARN` secret where
one exists (`production`), else from the state bucket's name, which ends in it
(`petbot-tfstate-<account-id>`; inference from the README's naming, not verified against
the live bucket: the first dev deploy shows it, and fails at that step if not). The `dev`
GitHub environment is created by the first run that references it, with no protection
rules, so it admits every branch (documented: GitHub, *Using environments for deployment*).

### Bootstrap: one root of trust, an environment map

`bootstrap/`'s `var.environments` lists each stage: `name_prefix`, its GitHub environment,
and whether it runs the edge, sets a budget, calls mantle, and which outside parameters it
may read to copy. Each gets a deploy role trusting only its GitHub environment
(`petbot-github-deploy-prod` from `production`, `petbot-github-deploy-dev` from `dev`), its
own workload boundary, and a deploy policy scoped to its prefix, including its own
`/<name_prefix>/*` parameters; the edge's IAM-user and Lightsail rights and Budgets only
where they apply. One bootstrap manages all of them, so the account-global GitHub OIDC
provider stays one resource with no toggle. The operator may invoke each stage's core.

The `dev` GitHub environment admits **every branch**: deploying an unmerged branch is the
point. Its role is the control: `petbot-dev-*` matches nothing else, and it has no
Lightsail (whose GUID ARNs can't be name-scoped), IAM-user or Budgets rights.

A third, transitional entry, `legacy` (`name_prefix = "petbot"`), is the production stack
as it stands: its role keeps the name `petbot-github-deploy`, and `moved` blocks keep that
role, its policy and `petbot-workload-boundary` in place. Rendered offline against the
code before this change, with fake credentials: the role, its trust and the boundary are
identical, and its policy only gains the parameter statements every stage has (manage
`/petbot/*`, which its retirement uses). It is exempt from the containment rule and is
removed once the stack it deploys is destroyed (below).

### Deploy: `deploy.yml`'s `environment` input

A manual run picks `production` (default) or `dev`; a push to `main` always deploys
production. The environment sets the job's GitHub environment, the stage (`prod` | `dev`),
its prefix, deploy role and settings file, and the state key `<prefix>/terraform.tfstate`;
the edge is built when the settings enable it. Runs take turns per environment.

### Talking to it: the harness's `--lambda`

`python -m petbot.services.core.chat --lambda petbot-dev-core <conversation>` sends the
same conversation through `ProcessClient` + `LambdaTransport`, the frontend's own path; a
failed dispatch gets the frontend's fallback reply. In-process remains the default.

## Migrating production: `petbot` to `petbot-prod`

A Lambda's, ECR repository's, IAM role's or user's, DynamoDB table's and Lightsail
service's name can't change in place; a new name is a new resource. So the `petbot-prod`
stack is built **beside** the `petbot` one, in its own state, the edge is cut over, and
then the old stack is destroyed. Each step is a pull request; merging it runs the
pipelines, and each run waits for the owner's approval of a gated environment
(`production`, `bootstrap`) before it changes anything. The old stack is operated by its
own workflow, `legacy.yml`, from `stages/legacy.tfvars`. The pull requests are listed in
`deploy/terraform/README.md`, "Migrating production to petbot-prod".

| Resource | Today (`petbot`) | After (`petbot-prod`) | How |
| --- | --- | --- | --- |
| Core Lambda, role, log group | `petbot-core`, `petbot-core-role`, `/aws/lambda/petbot-core` | `petbot-prod-core`, … | new, beside the old; old destroyed with its stack, and its logs (30-day retention) with it |
| ECR repos | `petbot-core`, `petbot-edge` | `petbot-prod-core`, `petbot-prod-edge` | new; CI pushes fresh images. The old images go with their repos (`force_delete`): a rollback past the migration redeploys a commit, not an old image |
| Lightsail service | `petbot-edge` | `petbot-prod-edge` | new; the cutover. Its private `.service.local` name changes; nothing dials the edge |
| Edge IAM user and key | `petbot-edge` | `petbot-prod-edge` | new user, new key; the old ones go with their stack |
| Claims table | `petbot-edge-claims` | `petbot-prod-edge-claims` | new; its claims expire within the hour (TTL), so nothing carries over |
| Budget, X-Ray log policy (if enabled) | `petbot-monthly`, `petbot-xray-transaction-search` | `petbot-prod-…` | new |
| SSM: Discord token | `/petbot/edge/discord_token` | `/petbot-prod/edge/discord_token` | copied by the prod stack (`ssm_parameters`, write-only); the old one deleted by `legacy.yml` after the destroy |
| SSM: Bedrock API key | `/petbot/core/bedrock_api_key` | none | production moves to `bedrock_mantle`; deleted by `legacy.yml` |
| SSM: Tavily key | `/petbot/core/tavily_api_key` | `/petbot-prod/core/tavily_api_key` | copied the same way (`stages/prod.tfvars`, bootstrap's `adopt_parameters`); the old one deleted by `legacy.yml`. Production sets no telemetry salt or booru key |
| Hand-made Bedrock key user | `petbot-bedrock-key` (outside Terraform) | none | bootstrap imports it (`import` block), then deletes it by removing the resource; `force_destroy` takes its policies and service-specific credentials (verified: provider source) |
| State | `petbot/terraform.tfstate` | `petbot-prod/terraform.tfstate` | new; the old object deleted by `legacy.yml` after the destroy |
| Deploy role, boundary | `petbot-github-deploy`, `petbot-workload-boundary` (scope `petbot-*`) | `petbot-github-deploy-prod`, `petbot-prod-workload-boundary` | created by bootstrap now; the old pair is `legacy` until its stack is gone (a boundary can't be deleted while attached), then removed |
| GitHub environment | `production` | `production` | kept; nothing in it changes |

**Cutover and downtime.** Two connected edges would both answer every message (each claims
it in its own table), so the old edge is paused (`edge_paused = true` in
`stages/legacy.tfvars`, applied by `legacy.yml`) and the new one enabled
(`edge_enabled = true` in `stages/prod.tfvars`, applied by `deploy.yml`) in one pull
request. Both runs wait for approval, so their order is the owner's: approving the pause
first means PetBot is offline in Discord until the production run finishes and its
container connects (one deploy run: both images built, cached; the Lightsail service
created; the deployment pushed; no duration measured here); approving production first
means no downtime, but messages sent while both are connected get two answers. Rollback,
while the old stack exists, is reverting that pull request: the new edge is removed and the
old service re-enabled. Whether re-enabling restarts its last deployment is not documented
in what was checked; `legacy.yml`'s plan of the revert shows what it will do.

**Between the first merge and the cutover**, `main` deploys to `petbot-prod`, not to the
stack serving Discord: keep that window short.

## Consequences

- An unmerged branch is deployable and testable against production's model before merge,
  with no Discord, no edge and no secret.
- Neither stage's CI role or workloads can reach the other's resources, state or
  parameters.
- Production loses its last hand-minted credential when it moves to `bedrock_mantle`.
- Dev is one slot: each deploy replaces the last.
- Anyone who can push a branch can run code with the dev role and the dev core's role.
  Their reach is dev's resources and the model (cost: inference tokens).
- GitHub's own settings stay outside this code: the existing environments' protection
  rules, the `TF_STATE_BUCKET` and `DEPLOY_ROLE_ARN` secrets the pipelines read, and the
  GitHub variables `deploy.yml` no longer reads (stale, harmless). Managing them as code
  takes the Terraform GitHub provider and a GitHub credential with admin rights on the
  repository, which GitHub only issues through its web interface (a GitHub App or a
  token): one hand step, like bootstrap's first apply, that this ADR does not take.
- A secret that exists nowhere in AWS yet (a new third-party key) can't enter from code:
  the third party issues it to a person. Copying covers every secret production has today;
  a new one would need a source the pipeline can read (for instance the 1Password
  Development vault through a service-account token, itself one hand-made credential).
