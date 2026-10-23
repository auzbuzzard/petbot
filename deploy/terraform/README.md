# PetBot deploy — Terraform

Infrastructure-as-code for PetBot 2.1: two deployables over one neutral core.

- **Core worker** — an AWS **Lambda** (container image) hosting math + booru
  search + the chat agent. It is **private**: no Function URL. The edge invokes it
  with the AWS SDK (`boto3 invoke`), authenticated by IAM.
- **Edge** — the always-on Discord gateway holder, on an **AWS Lightsail container
  service** (`nano`, flat-rate, public IPv4 bundled). It holds the gateway
  WebSocket, maps each `@mention` to a dispatched call, and invokes the worker.

The same stack deploys two stages, each under its own prefix: **prod**
(`petbot-prod-*`, core + edge) and **dev** (`petbot-dev-*`), a core worker alone
(`edge_enabled = false`), built from any branch and talked to through the chat
harness rather than Discord. See [Dev core](#dev-core-an-unmerged-branch-before-it-merges).
Production still runs under the pre-stage prefix `petbot` until it is migrated: see
[Migrating production to petbot-prod](#migrating-production-to-petbot-prod).

```
bootstrap/        root of trust: state bucket, GitHub OIDC, CI roles, workload boundary, operator access
*.tf              the core worker (Lambda + ECR + IAM) and edge (Lightsail) stack
backend.hcl.example       remote-state backend config (copy -> backend.hcl)
terraform.tfvars.example  inputs (copy -> terraform.tfvars); no secrets here
```

Images build from [`../Dockerfile.lambda`](../Dockerfile.lambda) (worker, arm64)
and [`../Dockerfile.edge`](../Dockerfile.edge) (edge, amd64).

## Topology

```
Discord ⇄ [ edge ]  --boto3 invoke (IAM)-->  [ core worker Lambda ]  math · booru · chat
          Lightsail container service          private, no public endpoint
```

The edge carries a **scoped IAM user** whose only permissions are
`lambda:InvokeFunction` and `lambda:GetFunctionConfiguration` (to wait out an
Inactive/Pending function) on the core worker, and `dynamodb:PutItem` /
`dynamodb:UpdateItem` on its `<name_prefix>-edge-claims` table (one copy answers each
message; see `claims.tf`). Its access key is injected into the
container's environment (Lightsail container services have no IAM instance roles),
and replaced every `edge_key_rotation_days` (default 90) on the next deploy after that.
No public, unauthenticated surface exists, so there is no LLM cost-abuse vector.

Both images live in **ECR**. The worker Lambda runs its image directly; the edge
**pulls** its image from ECR via Lightsail's private-registry access (an
auto-created "image puller" principal that `edge.tf` grants read on the edge
repo). One registry, one push mechanism — no `lightsailctl`, no image-ref
scraping.

## Prerequisites

- An AWS account with credentials in your shell (e.g. `aws sso login`).
- Terraform >= 1.11 (for S3-native state locking), Docker, and the AWS CLI.
- Secrets live in **SSM SecureString** parameters under each stage's `/<name_prefix>/`,
  the only path its workloads' boundary may read (`/petbot-prod/...`, `/petbot-dev/...`).
  A stage owns its parameters (`ssm_parameters` in `stages/<stage>.tfvars`,
  `parameters.tf`): each is created with the value of an existing parameter, read through
  an ephemeral resource and written write-only, so no value reaches the plan or the state.
  Production's Discord token is copied this way from the pre-migration
  `/petbot/edge/discord_token`. Keys need none: `bedrock_mantle` calls the model with the
  function's role; web search and the boorus run keyless.

  A secret that exists nowhere in AWS yet (a new third-party key) has no path in from
  code: its value is issued by the third party and someone has to enter it once. That is
  the one step this setup leaves outside the pipelines (docs/adr/0014).

  > Each process reads its secrets from SSM when it starts: Terraform passes it only
  > the parameter *names* (`SSM_SECRETS`, see `secrets.tf`), and its IAM identity may
  > read exactly those parameters. No secret value lands in the function's
  > configuration or in Terraform state. The exception is the edge's own AWS access
  > key: Lightsail has no IAM roles, so Terraform creates the key and it lives in state.

## Bootstrap (root of trust)

`bootstrap/` holds what the root stack's CI cannot grant itself: the remote-state
bucket, the **GitHub Actions OIDC provider**, the CI roles, the workload permissions
boundary and the operator's access. Its state lives in the same bucket, under
`bootstrap/terraform.tfstate`.

**Who may assume what.** Every OIDC role trusts exactly one GitHub environment (the
token's `sub` is `repo:auzbuzzard/petbot:environment:<name>` whenever a job references
an environment). Every environment but `dev` admits only `main`:

| Role | Assumed by | Environment | Gate |
| --- | --- | --- | --- |
| `petbot-github-deploy-prod` | `deploy.yml` (prod stack) | `production` | `main` only + required reviewer |
| `petbot-github-deploy-dev` | `deploy.yml` run for `dev` (dev stack) | `dev` | any branch |
| `petbot-github-deploy` | the pre-migration `petbot` stack (`legacy`); removed after the migration | `production` | `main` only + required reviewer |
| `petbot-github-bootstrap-plan` | `bootstrap.yml`, plan job (read-only) | `bootstrap-plan` | `main` only |
| `petbot-github-bootstrap-apply` | `bootstrap.yml`, apply job | `bootstrap` | `main` only + required reviewer |
| `petbot-operator` | the `claude` IAM user (`sts:AssumeRole`) | — | read-only |

No pull request, workflow run outside an environment, or other workflow (the AI review
bots hold `id-token: write`) can assume any of them, and no branch but `main` can assume
any but the dev role. The deploy roles are explicitly denied the access roles
(`petbot-github-*`, `petbot-operator`), so none can widen its own or anyone's permissions.

**Environments.** `var.environments` in `bootstrap/` lists each stage with its
`name_prefix`; `deploy.yml` maps the GitHub environment to the same prefix and to the
state key `<name_prefix>/terraform.tfstate`. Each gets its own deploy role and workload
boundary, and no stage's prefix may contain another's:

| Stage (`var.environments`) | GitHub environment | `name_prefix` | Stack | State key |
| --- | --- | --- | --- | --- |
| `prod` | `production` | `petbot-prod` | core + edge | `petbot-prod/terraform.tfstate` |
| `dev` | `dev` | `petbot-dev` | core only | `petbot-dev/terraform.tfstate` |
| `legacy` (until migrated) | `production` | `petbot` | core + edge | `petbot/terraform.tfstate` |

**A deploy role** is scoped by naming convention: it may manage resources named
`<name_prefix>-*` of its environment (ECR repos, the Lambda and its log group,
DynamoDB tables, IAM roles, plus IAM users and Lightsail where the stack runs the edge
and AWS Budgets where it sets one), its own state, and its own SSM parameters
(`/<name_prefix>/*`). Every role and user it creates must carry its
**`<name_prefix>-workload-boundary`** permissions boundary, so no policy CI writes
can grant a workload more than that ceiling (no IAM; data-plane access to the
stack's own resources). Adding resources to the root stack therefore needs **no
bootstrap change**; only a new AWS service does.

Neither stage reaches the other: `petbot-prod-*` and `petbot-dev-*` match nothing of
each other's, nor do their states and parameters. The dev role, reachable from any
branch, also has no Lightsail, IAM-user or Budgets rights. The `legacy` role's
`petbot-*` scope covers both stages; it exists only until the old stack is destroyed.

**Changing bootstrap** is a PR like any other. After it merges, `bootstrap.yml`
plans with the read-only role and posts the plan, with its digest, to the run's
summary; the run then waits on the `bootstrap` environment until a required reviewer
approves, plans again, and applies only if that plan has the reviewed digest (otherwise
re-run the workflow and review the new plan). No plan file or state leaves the runner;
the plan text in the public log shows what this directory's code already shows, plus
the account ID. A PR that needs the new permission in its own deploy (a new AWS
service) lands its bootstrap change first.

**GitHub settings.** The existing environments were configured once by a repo admin
(Settings → Environments), with *Selected branches and tags → Branch `main`*, not
*Protected branches only*: that option admits every branch when the repo has no classic
branch protection rules (a ruleset may not count), and it would admit any branch
protected later. These are part of the trust model: without the branch rule, any branch
could reference the environment and assume its role.

| Environment | Deployment branches | Required reviewers |
| --- | --- | --- |
| `production` | Selected: `main` | the repo owner |
| `dev` | All branches (created by its first deploy, with no rules) | none |
| `bootstrap-plan` | Selected: `main` | none |
| `bootstrap` | Selected: `main` | the repo owner |

`dev` admits every branch on purpose: deploying an unmerged branch is what it is for.
Its role's reach is what keeps that safe (above). GitHub creates an environment the first
time a workflow references it, without rules or secrets, so `dev` needs no setting.

**Seeding (once per account, by an admin).** The pipeline can't create the roles it
assumes, so the first apply is by hand, with admin credentials (e.g. CloudShell with
Terraform installed):

```sh
# A new account only: create the bucket the state will live in, then adopt it below.
aws s3api create-bucket --bucket petbot-tfstate-<account-id> --region us-east-1   # elsewhere also pass --create-bucket-configuration LocationConstraint=<region>

cd deploy/terraform/bootstrap
cp backend.hcl.example backend.hcl   # fill in the bucket name
terraform init -backend-config=backend.hcl
terraform import -var "state_bucket=petbot-tfstate-<account-id>" aws_s3_bucket.state petbot-tfstate-<account-id>   # new account only
terraform import -var "state_bucket=petbot-tfstate-<account-id>" aws_iam_user.operator claude                       # if the user exists
terraform apply  -var "state_bucket=petbot-tfstate-<account-id>"
cd .. && cp backend.hcl.example backend.hcl   # root stack backend
```

Then set the GitHub secrets below from `terraform output`. From here on, no one applies
bootstrap by hand. The state bucket is named `petbot-tfstate-<account-id>`: a stage
whose environment has no `DEPLOY_ROLE_ARN` (dev) takes the account ID from it.

The state bucket and the role ARNs carry the AWS account ID, and the workflow logs are
public like the repository, so they are **Secrets**, which GitHub masks in every log and
summary:

| GitHub Actions secret | Scope | Value | Read for |
| --- | --- | --- | --- |
| `TF_STATE_BUCKET` | repo | the state bucket name | the backend; the account ID where no `DEPLOY_ROLE_ARN` is set |
| `DEPLOY_ROLE_ARN` | `production` | a deploy role's ARN in this account | the account ID only: each stage's role name is code (`.github/scripts/deploy-role.sh`) |
| `BOOTSTRAP_PLAN_ROLE_ARN` | `bootstrap-plan` | the bootstrap plan role ARN | `bootstrap.yml` |
| `BOOTSTRAP_APPLY_ROLE_ARN` | `bootstrap` | the bootstrap apply role ARN | `bootstrap.yml` |

The credentials step also masks the account ID wherever it appears after it (ARNs,
registry URLs, Terraform output). The one **Variable** is `AWS_REGION` (repo level).

**Stage settings are code.** Everything else a deploy needs is in
`stages/<stage>.tfvars` (`prod`, `dev`, and `legacy` until the old stack is gone),
which `deploy.yml` hands to every Terraform command: the model and endpoint, whether the
edge runs, the parameters the stage owns. Changing a setting is a pull request. The
GitHub variables the pipeline used to read (`CHAT_LLM_*`, `TAVILY_API_KEY_SSM_PARAMETER`,
`OBSERVABILITY_*`, …) are no longer read.

The dev core reads no secret: it calls the model with its role, and its boundary can't
read production's `/petbot-prod/*` parameters, so web search runs on the keyless `ddgs`
fallback and the boorus unauthenticated.

**Provider notes.** `bedrock` = the Converse API with IAM auth (no key) — Nova /
Claude. **Gemma 4 is served only via Bedrock's OpenAI-compatible "mantle"
endpoint**, reached two ways: `chat_llm_kind = "bedrock_mantle"` signs each request with
the function's own role (SigV4; the role gets `bedrock-mantle:CreateInference` and no
key exists), and `chat_llm_kind = "openai_compatible"` sends a **Bedrock API key** from
SSM. `bedrock_mantle` also needs the stage's workload boundary to allow mantle
(`bedrock_mantle = true` in `var.environments`; both stages have it, `legacy` not). The
`openai_compatible` kind also points at a self-hosted Ollama/vLLM later — just a
different base URL.

## Operator access (read-only triage)

`bootstrap/operator.tf` gives the operator (an agent such as Claude, or a human on
call) what triage needs and nothing more: the stack's Lambda logs, the edge's
container logs and deployments, function config, the stack's DynamoDB tables, ECR
images, IAM reads and policy simulation, metrics, traces and CloudTrail, plus
`lambda:InvokeFunction` on each environment's core worker for integration tests (the
chat harness's `--lambda`). No secrets
(`ssm:GetParameter`), no state bucket (Terraform state holds the edge's AWS access
key), no writes.

The IAM user `operator_user` (default `claude`) may only assume `petbot-operator`
(1-hour sessions). Its access keys are created out of band (console or
`aws iam create-access-key`), never in Terraform state. Point the operator's AWS
config at the role, with the user's keys in the environment:

```ini
# ~/.aws/config
[default]
role_arn            = arn:aws:iam::<account-id>:role/petbot-operator
credential_source   = Environment
region              = us-east-1
```

An existing user is adopted at seeding (see above). The user must hold nothing
besides that `sts:AssumeRole`: AWS's `ReadOnlyAccess`, for one, reads every S3
object, including the state. Bootstrap enforces it three ways:

- the user's **permissions boundary** (`petbot-operator-user-boundary`) allows only
  assuming `petbot-operator`, so a group, attached or inline policy added by hand
  grants nothing;
- its inline policies are exactly `assume-petbot-operator` and it has no attached
  policies (`aws_iam_user_policies_exclusive`,
  `aws_iam_user_policy_attachments_exclusive`): the next plan shows any other as
  drift and the apply removes it;
- the deploy role is denied all IAM on it, and `operator_user` may not start with
  `<name_prefix>-` (the deploy role's user scope).

Changes to access go through the bootstrap pipeline, never through this role.

## CI deploy (the steady-state path)

`.github/workflows/deploy.yml` does the whole rollout via OIDC: build + push both
images to ECR (arm64 worker, amd64 edge), then `terraform apply` (the Lightsail
edge pulls its image from ECR). A push to `main` (or a manual *Actions → Deploy
→ Run workflow*) ships it. **No deploy is run from a developer machine.**

## Dev core (an unmerged branch, before it merges)

Deploy any branch's core to dev (`stages/dev.tfvars`), then talk to it with the same
conversations the in-process harness runs:

```sh
gh workflow run deploy.yml --ref <branch> -f environment=dev
python -m petbot.services.core.chat --lambda petbot-dev-core conversations/leetcode-daily.json
python -m petbot.services.core.chat --lambda petbot-dev-core --say "what's today's leetcode daily?"
```

The harness invokes the function the way the edge does (`LambdaTransport`), with
your AWS credentials (`AWS_REGION` or a profile's region; the `petbot-operator` role
may invoke it). The turn runs in the Lambda, on its network, configuration and time
budget, so it answers what in-process runs can't: whether a site answers AWS's
addresses, whether the function's IAM and packaging work. Its tool calls are in its
log group, `/aws/lambda/petbot-dev-core`.

Dev is one slot: each run replaces what the last one deployed, and runs take turns
(`concurrency`). Idle, a Lambda costs nothing; what remains is ECR storage for its
images (the lifecycle policy keeps the last `ecr_keep_last_images`) and its retained
logs. Tearing dev down has no pipeline yet; it would go the way `legacy.yml` retires
the old stack.

## Migrating production to petbot-prod

Production runs as the pre-stage `petbot` stack (`petbot-core`, `petbot-edge`, state
`petbot/terraform.tfstate`, parameters under `/petbot/`). Names can't change in place, so
`petbot-prod` is built beside it, the edge is cut over, and the old stack is destroyed.
The per-resource decisions and the downtime are in
[ADR 0014](../../docs/adr/0014-dev-core-environment.md#migrating-production-petbot-to-petbot-prod).

Every step is a pull request. Merging it runs the pipelines, and each run waits for the
owner's approval of `production` or `bootstrap`, after which its log shows the plan it
applies. The old stack is operated by `.github/workflows/legacy.yml` from
`stages/legacy.tfvars`, as its own deploy role (`petbot-github-deploy`).

1. **This change.** Merging it runs three pipelines; approve them in this order:
   - `bootstrap.yml`: three moves to `["legacy"]`; a role, policy and boundary each for
     `prod` and `dev`; the parameter statements added to legacy's policy; the operator's
     and the pipeline roles' updates (`petbot-prod-core`, `petbot-dev-core`,
     `petbot-bedrock-key`).
   - `legacy.yml`: its plan moves ten edge resources to `[0]` and changes nothing. A
     change in it means `stages/legacy.tfvars` doesn't describe the live stack: fix the
     file in a pull request rather than applying.
   - `deploy.yml` (production): creates `petbot-prod-core`, its registry, role and log
     group, and `/petbot-prod/edge/discord_token` and `/petbot-prod/core/tavily_api_key`,
     copied from the legacy parameters (their values show as write-only, never printed). No
     edge (`edge_enabled = false`); the legacy stack keeps serving Discord. If this run
     reached AWS before bootstrap's apply, it failed to assume `petbot-github-deploy-prod`:
     re-run it.

   Then talk to the new core, and deploy a branch to dev:

   ```sh
   python -m petbot.services.core.chat --lambda petbot-prod-core conversations/leetcode-daily.json
   ```

   From here until the cutover, `main` deploys to `petbot-prod`, not to the stack
   serving Discord: keep this window short.

2. **Cutover.** One pull request: `edge_enabled = true` in `stages/prod.tfvars` and
   `edge_paused = true` in `stages/legacy.tfvars`. Merging it runs `deploy.yml`
   (production: the new edge) and `legacy.yml` (pauses the old edge's service, which
   shuts its containers down). The order you approve them in sets the trade-off: the
   pause first, and PetBot is offline in Discord until the production run's container
   connects (one deploy run; no duration measured yet); production first, and messages
   sent while both are connected get two answers. **Rollback** is reverting this pull
   request.

3. **Retire the old stack**, after a soak. One pull request:
   - `retired = true` in `stages/legacy.tfvars`: `legacy.yml` plans the destroy, applies
     it once approved, then deletes `retired_parameters` (the old Discord token, Bedrock
     API key and Tavily key) and the old state object;
   - in `bootstrap/`, adopt the hand-made Bedrock key user, so the next step can delete
     it through the pipeline:

     ```hcl
     import {
       to = aws_iam_user.retired["petbot-bedrock-key"]
       id = "petbot-bedrock-key"
     }

     resource "aws_iam_user" "retired" {
       for_each      = toset(var.retiring_users)
       name          = each.key
       force_destroy = true
     }
     ```

     Its plan imports the user and sets `force_destroy`; read it for any other change
     (the user's path or tags) and match the block to it.

4. **Remove `legacy`.** One pull request: delete the `legacy` entry and its three
   `moved` blocks from `bootstrap/main.tf`, the `adopt_parameters` of `prod`, the
   `retiring_users` default and the `aws_iam_user.retired` block (with its import);
   delete `stages/legacy.tfvars`, `.github/workflows/legacy.yml` and the root `moved.tf`;
   set the source of `/petbot-prod/edge/discord_token` in `stages/prod.tfvars` to `""`.
   Bootstrap's plan deletes `petbot-github-deploy`, its policy, `petbot-workload-boundary`
   (no longer attached) and the `petbot-bedrock-key` user, with its policies and its
   service-specific credential (`force_destroy`).

What stays outside this code: GitHub's own settings (see *GitHub settings*). After step 4,
the `production` secret `DEPLOY_ROLE_ARN` names a deleted role; the pipelines read only
its account ID, so it keeps working.

## Deploy (manual / break-glass)

Because the function is pinned to its image digest and the edge service must grant
ECR-pull access before the edge deployment is created, the first apply is staged:

```sh
cp terraform.tfvars.example terraform.tfvars   # set region, chat_llm_*, SSM names
terraform init -backend-config=backend.hcl

# 1. Create both ECR repos, the Lightsail service, and the edge repo policy.
terraform apply \
  -target=aws_ecr_repository.this -target=aws_ecr_repository.edge \
  -target=aws_lightsail_container_service.edge -target=aws_ecr_repository_policy.edge

# 2. Push both images to ECR (one login covers both repos).
CORE=$(terraform output -raw ecr_repository_url)
EDGE=$(terraform output -raw edge_ecr_repository_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${CORE%/*}"
docker build --platform linux/arm64 -f ../Dockerfile.lambda -t "$CORE:latest" ../.. && docker push "$CORE:latest"
docker build --platform linux/amd64 -f ../Dockerfile.edge   -t "$EDGE:latest" ../.. && docker push "$EDGE:latest"

# 3. Stand up the worker + edge deployment (the edge pulls its image from ECR).
terraform apply -var 'image_tag=latest' -var 'edge_image_tag=latest'

terraform output core_function_arn          # the edge's WORKER__FUNCTION_NAME target
terraform output edge_container_service_name
```

For subsequent deploys, push new images (prefer a unique tag, e.g. the git SHA)
and re-`apply` with the new `image_tag` / `edge_image_tag`.

## Migrating from the old interactions stack (one-time)

PetBot 2.0 deployed a single public **interactions** Lambda (`petbot-interactions`,
state key `interactions/terraform.tfstate`). 2.1 replaces it with the private core
worker + the edge, under a new state key (`petbot/terraform.tfstate`) and new
names. The old stack is **decommissioned**: once, run `terraform destroy` against
the old `interactions/…` state (or delete the orphaned function, ECR repo, and
role in the console). Nothing imports from the old state.

## Cost & retention

- **Edge:** Lightsail `nano` ~$7/mo flat (public IPv4 + 500 GB transfer bundled).
- **Worker:** Lambda — ~$0 at this scale (scale-to-zero); chat inference is the
  only real variable (cents–low-$/mo).
- **ECR lifecycle** (`retention.tf`) expires old/untagged images in both repos.
- **CloudWatch Logs** retain `log_retention_days`; the group is owned here so
  `terraform destroy` removes it.
- **Cost alerts** are opt-in: set `monthly_budget_usd` + `budget_alert_emails`.

## Teardown

```sh
terraform destroy
cd bootstrap && terraform init -backend-config=backend.hcl
```

Bootstrap's state lives in the bucket it destroys, and the bucket is
`prevent_destroy`, so: remove the bucket's `prevent_destroy`, delete the
`backend "s3" {}` block from `bootstrap/main.tf`, run `terraform init -migrate-state`,
empty the versioned bucket (console → *Empty*), then
`terraform destroy -var "state_bucket=petbot-tfstate-<your-account-id>"`.

## CI checks

`.github/workflows/terraform.yml` runs `fmt -check` + `validate` on PRs, and
`terraform test` on both stacks (the root stack's `tests/` plans prod and dev against mock
providers; bootstrap's renders each stage's IAM and checks no prefix contains another's),
with no AWS credentials. `.github/workflows/deploy.yml` runs the OIDC build/apply
pipeline above.
