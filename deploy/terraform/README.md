# PetBot deploy — Terraform

Infrastructure-as-code for PetBot 2.1: two deployables over one neutral core.

- **Core worker** — an AWS **Lambda** (container image) hosting math + booru
  search + the chat agent. It is **private**: no Function URL. The edge invokes it
  with the AWS SDK (`boto3 invoke`), authenticated by IAM.
- **Edge** — the always-on Discord gateway holder, on an **AWS Lightsail container
  service** (`nano`, flat-rate, public IPv4 bundled). It holds the gateway
  WebSocket, maps each `@mention` to a dispatched call, and invokes the worker.

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
`dynamodb:UpdateItem` on its `petbot-edge-claims` table (one copy answers each
message; see `claims.tf`). Its access key is injected into the
container's environment (Lightsail container services have no IAM instance roles).
No public, unauthenticated surface exists, so there is no LLM cost-abuse vector.

Both images live in **ECR**. The worker Lambda runs its image directly; the edge
**pulls** its image from ECR via Lightsail's private-registry access (an
auto-created "image puller" principal that `edge.tf` grants read on the edge
repo). One registry, one push mechanism — no `lightsailctl`, no image-ref
scraping.

## Prerequisites

- An AWS account with credentials in your shell (e.g. `aws sso login`).
- Terraform >= 1.11 (for S3-native state locking), Docker, and the AWS CLI.
- Secrets live in **SSM SecureString** parameters, created out-of-band so their
  values never touch Terraform state as managed resources:

  ```sh
  # The edge's Discord bot token (read into the Lightsail container env at apply).
  aws ssm put-parameter --type SecureString \
    --name /petbot/edge/discord_token --value "<bot token>"

  # Chat LLM key — only for the key-based providers:
  #   openai_compatible (e.g. Bedrock's Gemma 4 "mantle" endpoint): a Bedrock API
  #   key (Bedrock console -> API keys). bedrock (Converse + IAM) needs no key.
  # aws ssm put-parameter --type SecureString \
  #   --name /petbot/core/bedrock_api_key --value "<bedrock api key>"
  # openrouter instead:
  # aws ssm put-parameter --type SecureString \
  #   --name /petbot/core/openrouter_api_key --value "<key>"

  # Optional web search key (Tavily, 1,000 free searches/month). Without it the
  # chat agent's web_search runs on the keyless ddgs fallback alone:
  # aws ssm put-parameter --type SecureString \
  #   --name /petbot/core/tavily_api_key --value "tvly-..."

  # Optional booru auth:
  # aws ssm put-parameter --type SecureString --name /petbot/core/derpibooru_api_key --value "..."
  ```

  > Note: SSM values referenced by Terraform are injected into the Lambda /
  > container environment at apply time, so they do land in Terraform **state**.
  > The state bucket is encrypted, versioned, and private to contain this;
  > runtime SSM fetch (state stays secret-free) is a future hardening (#17).

## Bootstrap (root of trust)

`bootstrap/` holds what the root stack's CI cannot grant itself: the remote-state
bucket, the **GitHub Actions OIDC provider**, the CI roles, the workload permissions
boundary and the operator's access. Its state lives in the same bucket, under
`bootstrap/terraform.tfstate`.

**Who may assume what.** Every OIDC role trusts exactly one GitHub environment (the
token's `sub` is `repo:auzbuzzard/petbot:environment:<name>` whenever a job references
an environment), and each environment admits only `main`:

| Role | Assumed by | Environment | Gate |
| --- | --- | --- | --- |
| `petbot-github-deploy` | `deploy.yml` (root stack) | `production` | `main` only + required reviewer |
| `petbot-github-bootstrap-plan` | `bootstrap.yml`, plan job (read-only) | `bootstrap-plan` | `main` only |
| `petbot-github-bootstrap-apply` | `bootstrap.yml`, apply job | `bootstrap` | `main` only + required reviewer |
| `petbot-operator` | the `claude` IAM user (`sts:AssumeRole`) | — | read-only |

No pull request, other branch or other workflow (the AI review bots hold
`id-token: write`) can assume any of them. The deploy role is explicitly denied the
access roles (`<name_prefix>-github-*`, `<name_prefix>-operator`), so it can't widen
its own or anyone's permissions.

**The deploy role** is scoped by naming convention: it may manage resources named
`<name_prefix>-*` (ECR repos, the Lambda and its log group, DynamoDB tables, IAM
roles and users). Every role and user it creates must carry the
**`<name_prefix>-workload-boundary`** permissions boundary, so no policy CI writes
can grant a workload more than that ceiling (no IAM; data-plane access to the
stack's own resources). Adding resources to the root stack therefore needs **no
bootstrap change**; only a new AWS service does.

**Changing bootstrap** is a PR like any other. After it merges, `bootstrap.yml`
plans with the read-only role and posts the plan to the run's summary; the run then
waits on the `bootstrap` environment until a required reviewer approves, and applies
that exact plan. A PR that needs the new permission in its own deploy (a new AWS
service) lands its bootstrap change first.

**GitHub settings** (Settings → Environments; one time, by a repo admin). Use
*Selected branches and tags → Branch `main`*, not *Protected branches only*: that option
admits every branch when the repo has no classic branch protection rules (a ruleset may
not count), and it would admit any branch protected later. These are
part of the trust model: without the branch rule, any branch could reference the
environment and assume its role.

| Environment | Deployment branches | Required reviewers |
| --- | --- | --- |
| `production` | Selected: `main` | the repo owner |
| `bootstrap-plan` | Selected: `main` | none |
| `bootstrap` | Selected: `main` | the repo owner |

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

Then set the GitHub variables below from `terraform output`. From here on, no one
applies bootstrap by hand.

Set the following repo **Variables** (Settings → Secrets and variables → Actions
→ Variables — these are non-secret; the actual secret *values* live in SSM,
referenced here only by parameter name). The deploy reads them as `TF_VAR_*`:

| GitHub Actions variable | Value | Where it comes from |
| --- | --- | --- |
| `DEPLOY_ROLE_ARN` | the deploy role ARN | `terraform -chdir=bootstrap output deploy_role_arn` |
| `BOOTSTRAP_PLAN_ROLE_ARN` | the bootstrap plan role ARN | `terraform -chdir=bootstrap output bootstrap_plan_role_arn` |
| `BOOTSTRAP_APPLY_ROLE_ARN` | the bootstrap apply role ARN | `terraform -chdir=bootstrap output bootstrap_apply_role_arn` |
| `AWS_REGION` | e.g. `us-east-1` | your choice (match `backend.hcl` / SSM region) |
| `TF_STATE_BUCKET` | the state bucket name | the `state_bucket` you chose above |
| `CHAT_LLM_KIND` | `bedrock` \| `openai_compatible` \| `openrouter` | your choice of provider |
| `CHAT_LLM_MODEL` | the model id | e.g. `google.gemma-4-31b` (Gemma 4 via mantle), a Bedrock Converse model, or an OpenRouter model |
| `CHAT_LLM_BASE_URL` | endpoint URL | **only** for `openai_compatible`, e.g. `https://bedrock-mantle.us-east-1.api.aws/openai/v1`; unset otherwise |
| `CHAT_LLM_API_KEY_SSM_PARAMETER` | e.g. `/petbot/core/bedrock_api_key` | for `openai_compatible` + `openrouter`; **unset** for `bedrock` |
| `TAVILY_API_KEY_SSM_PARAMETER` | e.g. `/petbot/core/tavily_api_key` | optional; the web search key. Unset ⇒ keyless `ddgs` search only |

**Provider notes.** `bedrock` = the Converse API with IAM auth (no key) — Nova /
Claude. **Gemma 4 is served only via Bedrock's OpenAI-compatible "mantle"
endpoint**, so for Gemma 4 use `CHAT_LLM_KIND=openai_compatible` with the
`CHAT_LLM_BASE_URL` above and a **Bedrock API key** in SSM. The same
`openai_compatible` kind also points at a self-hosted Ollama/vLLM later — just a
different base URL.

That's the complete list — once these Variables and the SSM secrets above exist,
a push to `main` runs a green deploy. (Merging the PR alone does **not** create
them; this one-time setup is yours to do.)

## Operator access (read-only triage)

`bootstrap/operator.tf` gives the operator (an agent such as Claude, or a human on
call) what triage needs and nothing more: the stack's Lambda logs, the edge's
container logs and deployments, function config, the stack's DynamoDB tables, ECR
images, IAM reads and policy simulation, metrics, traces and CloudTrail, plus
`lambda:InvokeFunction` on the core worker for integration tests. No secrets
(`ssm:GetParameter`), no state bucket (Terraform state holds the injected secrets),
no writes.

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
besides that `sts:AssumeRole` (no group, no attached policy). AWS's
`ReadOnlyAccess`, for one, reads every S3 object, including the state. Changes to
access go through the bootstrap pipeline, never through this role.

## CI deploy (the steady-state path)

`.github/workflows/deploy.yml` does the whole rollout via OIDC: build + push both
images to ECR (arm64 worker, amd64 edge), then `terraform apply` (the Lightsail
edge pulls its image from ECR). A push to `main` (or a manual *Actions → Deploy
→ Run workflow*) ships it. **No deploy is run from a developer machine.**

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

`.github/workflows/terraform.yml` runs `fmt -check` + `validate` on PRs (no AWS
credentials needed). `.github/workflows/deploy.yml` runs the OIDC build/apply
pipeline above.
