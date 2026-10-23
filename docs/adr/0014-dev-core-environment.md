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
and policies, claims table) is counted on `var.edge_enabled`. A dev apply creates the
core's ECR repo, role, log group and Lambda (`petbot-dev-core`) and nothing else. A
mock-provider `terraform test` plans both stages in CI. The edge's Discord-token parameter
defaults to `/<name_prefix>/edge/discord_token`.

### Bootstrap: one root of trust, an environment map

`bootstrap/`'s `var.environments` lists each stage: `name_prefix`, its GitHub environment,
and whether it runs the edge, sets a budget, calls mantle. Each gets a deploy role trusting
only its GitHub environment (`petbot-github-deploy-prod` from `production`,
`petbot-github-deploy-dev` from `dev`), its own workload boundary, and a deploy policy
scoped to its prefix; the edge's IAM-user and Lightsail rights and Budgets only where they
apply. One bootstrap manages all of them, so the account-global GitHub OIDC provider stays
one resource with no toggle. The operator may invoke each stage's core.

The `dev` GitHub environment admits **every branch**: deploying an unmerged branch is the
point. Its role is the control: `petbot-dev-*` matches nothing else, and it has no
Lightsail (whose GUID ARNs can't be name-scoped), IAM-user or Budgets rights.

A third, transitional entry, `legacy` (`name_prefix = "petbot"`), is the production stack
as it stands: its role keeps the name `petbot-github-deploy`, and `moved` blocks keep that
role, its policy and `petbot-workload-boundary` in place. Rendered offline against the
code before this change, with fake credentials, they are identical. It is exempt from the
containment rule and is removed once the stack it deploys is destroyed (below).

### Deploy: `deploy.yml`'s `environment` input

A manual run picks `production` (default) or `dev`; a push to `main` always deploys
production. The environment sets the job's GitHub environment (so its role and variables),
the prefix (`petbot-prod` | `petbot-dev`), the state key `<prefix>/terraform.tfstate` and
whether the edge is built: never for dev; for production unless its variable
`EDGE_ENABLED` is `false`, which holds a new production core's edge off while the old
stack still serves. Runs take turns per environment.

### Talking to it: the harness's `--lambda`

`python -m petbot.services.core.chat --lambda petbot-dev-core <conversation>` sends the
same conversation through `ProcessClient` + `LambdaTransport`, the frontend's own path; a
failed dispatch gets the frontend's fallback reply. In-process remains the default.

## Migrating production: `petbot` to `petbot-prod`

A Lambda's, ECR repository's, IAM role's or user's, DynamoDB table's and Lightsail
service's name can't change in place; a new name is a new resource. So the `petbot-prod`
stack is built **beside** the `petbot` one, in its own state, the edge is cut over, and
then the old stack is destroyed. Nothing is applied until the user approves each step; the
commands are in `deploy/terraform/README.md`, "Migrating production to petbot-prod".

| Resource | Today (`petbot`) | After (`petbot-prod`) | How |
| --- | --- | --- | --- |
| Core Lambda, role, log group | `petbot-core`, `petbot-core-role`, `/aws/lambda/petbot-core` | `petbot-prod-core`, … | new, beside the old; old destroyed with its stack. Its logs (30-day retention) go with it unless exported first |
| ECR repos | `petbot-core`, `petbot-edge` | `petbot-prod-core`, `petbot-prod-edge` | new; CI pushes fresh images. The old images are deleted with their repos (`force_delete`): a rollback past the migration redeploys a commit rather than an old image |
| Lightsail service | `petbot-edge` | `petbot-prod-edge` | new; the cutover. Its private `.service.local` name changes; nothing dials the edge, so nothing depends on it |
| Edge IAM user and key | `petbot-edge` | `petbot-prod-edge` | new user, new key; the old ones are destroyed with their stack |
| Claims table | `petbot-edge-claims` | `petbot-prod-edge-claims` | new; its claims expire within the hour (TTL), so nothing carries over |
| Budget, X-Ray log policy (if enabled) | `petbot-monthly`, `petbot-xray-transaction-search` | `petbot-prod-…` | new |
| SSM: Discord token | `/petbot/edge/discord_token` | `/petbot-prod/edge/discord_token` | value copied by the user; old deleted after |
| SSM: Bedrock API key | `/petbot/core/bedrock_api_key` | none | retired: production switches to `bedrock_mantle`. Its hand-made `petbot-bedrock-key` IAM user's credential can then be deleted |
| SSM: optional keys (Tavily, salt, boorus), if set | `/petbot/core/…` | `/petbot-prod/core/…` | copied, and the `production` variables repointed |
| State | `petbot/terraform.tfstate` | `petbot-prod/terraform.tfstate` | new; the old one is emptied by the destroy, then may be deleted |
| Deploy role, boundary | `petbot-github-deploy`, `petbot-workload-boundary` (scope `petbot-*`) | `petbot-github-deploy-prod`, `petbot-prod-workload-boundary` | created by bootstrap now; the old pair is `legacy` until its stack is gone (a boundary can't be deleted while attached), then removed by a bootstrap PR |
| GitHub environment | `production` | `production` | kept; its `DEPLOY_ROLE_ARN` secret and model variables change |

**Order.** (1) Before merging, set `production`'s `EDGE_ENABLED=false`, so the deploy the
merge starts brings up no second edge. (2) Merge; approve bootstrap's run once its plan
shows the three moves to `legacy`, the new prod and dev roles, policies and boundaries, and
the operator's update. (3) Repoint `production` (role ARN, `bedrock_mantle`, parameter
names) and copy the parameters; then let production deploy: `petbot-prod-core` and its
registry come up beside the live stack, which keeps serving untouched. (4) Talk to
`petbot-prod-core` with `--lambda`. (5) Cut over. (6) After a soak, destroy the old stack,
delete the old parameters and state, and land the bootstrap PR removing `legacy`.

**Cutover and downtime.** Two connected edges would both answer every message (each claims
it in its own table), so the old edge stops before the new one starts: disable the old
Lightsail service (its containers shut down: documented, Lightsail API), then deploy
production with `EDGE_ENABLED` unset. PetBot is offline in Discord from the disable until
the new container connects: one production deploy run, which builds both images (cached),
creates the Lightsail service and pushes the deployment. No duration has been measured
here. The alternative is no downtime at the cost of duplicates: start the new edge first
and disable the old one once the new one is connected, so messages in between get two
answers. Rollback, while the old stack exists: set `EDGE_ENABLED=false` and redeploy
production (removing the new edge), and re-enable the old service. Whether re-enabling
restarts its last deployment is not documented in what was checked; if it doesn't, the old
stack's last deployment is recreated from the console or CLI.

**Between merge and cutover**, `main` deploys to `petbot-prod`, not to the stack serving
Discord: keep that window short.

## Consequences

- An unmerged branch is deployable and testable against production's model before merge,
  with no Discord, no edge and no secret.
- Neither stage's CI role or workloads can reach the other's resources, state or
  parameters.
- Production loses its last hand-minted credential when it moves to `bedrock_mantle`.
- Dev is one slot: each deploy replaces the last.
- Anyone who can push a branch can run code with the dev role and the dev core's role.
  Their reach is dev's resources and the model (cost: inference tokens).
- GitHub's environment settings (`dev`'s branch rule, each environment's `DEPLOY_ROLE_ARN`
  secret and model variables, `EDGE_ENABLED`) are set by hand, as for the existing
  environments.
