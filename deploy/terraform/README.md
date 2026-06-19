# PetBot deploy — Terraform

Infrastructure-as-code for PetBot 2.1: two deployables over one neutral core.

- **Core worker** — an AWS **Lambda** (container image) hosting math + booru
  search + the chat agent. It is **private**: no Function URL. The edge invokes it
  with the AWS SDK (`boto3 invoke`), authenticated by IAM.
- **Edge** — the always-on Discord gateway holder, on an **AWS Lightsail container
  service** (`nano`, flat-rate, public IPv4 bundled). It holds the gateway
  WebSocket, maps each `@mention` to a dispatched call, and invokes the worker.

```
bootstrap/        one-time: S3 state bucket + GitHub OIDC deploy role
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

The edge carries a **scoped IAM user** whose only permission is
`lambda:InvokeFunction` on the core worker. Its access key is injected into the
container's environment (Lightsail container services have no IAM instance roles).
No public, unauthenticated surface exists, so there is no LLM cost-abuse vector.

## Prerequisites

- An AWS account with credentials in your shell (e.g. `aws sso login`).
- Terraform >= 1.11 (for S3-native state locking), Docker, and the AWS CLI.
- Secrets live in **SSM SecureString** parameters, created out-of-band so their
  values never touch Terraform state as managed resources:

  ```sh
  # The edge's Discord bot token (read into the Lightsail container env at apply).
  aws ssm put-parameter --type SecureString \
    --name /petbot/edge/discord_token --value "<bot token>"

  # Chat LLM: bedrock authenticates via the worker's IAM role (no secret).
  # For openrouter instead, store the API key and set chat_llm_kind=openrouter:
  # aws ssm put-parameter --type SecureString \
  #   --name /petbot/core/openrouter_api_key --value "<key>"

  # Optional booru auth:
  # aws ssm put-parameter --type SecureString --name /petbot/core/derpibooru_api_key --value "..."
  ```

  > Note: SSM values referenced by Terraform are injected into the Lambda /
  > container environment at apply time, so they do land in Terraform **state**.
  > The state bucket is encrypted, versioned, and private to contain this;
  > runtime SSM fetch (state stays secret-free) is a future hardening (#17).

## One-time: bootstrap remote state + OIDC

```sh
cd bootstrap
terraform init
terraform apply -var "state_bucket=petbot-tfstate-<your-account-id>"
cd ..
cp backend.hcl.example backend.hcl   # fill in the bucket name
```

The bootstrap stack also creates the **GitHub Actions OIDC provider** and the
**`petbot-github-deploy` IAM role** the CI pipeline assumes (no static AWS keys).
Wire its outputs as repo **variables** (Settings → Secrets and variables →
Actions → Variables):

| GitHub Actions variable | Value |
| --- | --- |
| `DEPLOY_ROLE_ARN` | `deploy_role_arn` bootstrap output |
| `AWS_REGION` | e.g. `us-east-1` (match `backend.hcl` / your SSM region) |
| `TF_STATE_BUCKET` | the `state_bucket` you chose above |

## CI deploy (the steady-state path)

`.github/workflows/deploy.yml` does the whole rollout via OIDC: build + push the
arm64 worker image (ECR) and the amd64 edge image (Lightsail registry), then
`terraform apply`. A push to `master` (or a manual *Actions → Deploy → Run
workflow*) ships it. **No deploy is run from a developer machine.**

## Deploy (manual / break-glass)

Because the worker is pinned to the image digest and the edge image needs its
Lightsail service to exist first, the first apply is staged:

```sh
cp terraform.tfvars.example terraform.tfvars   # set region, chat_llm_*, SSM names
terraform init -backend-config=backend.hcl

# 1. Create the ECR repo + the (empty) Lightsail container service.
terraform apply -target=aws_ecr_repository.this -target=aws_lightsail_container_service.edge

# 2. Build + push the worker image (arm64) to ECR.
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO%/*}"
docker build --platform linux/arm64 -f ../Dockerfile.lambda -t "$REPO:latest" ../..
docker push "$REPO:latest"

# 3. Build + push the edge image (amd64) to Lightsail; note the returned ref.
docker build --platform linux/amd64 -f ../Dockerfile.edge -t petbot-edge:latest ../..
aws lightsail push-container-image --service-name petbot-edge --label edge --image petbot-edge:latest
#   -> "Refer to this image as ":petbot-edge.edge.1" ..."

# 4. Stand up the worker + edge deployment.
terraform apply -var 'edge_image=:petbot-edge.edge.1'

terraform output core_function_arn          # the edge's WORKER__FUNCTION_NAME target
terraform output edge_container_service_name
```

For subsequent deploys, push new images (prefer a unique tag, e.g. the git SHA)
and re-`apply` with the new `image_tag` / `edge_image`.

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
- **ECR lifecycle** (`retention.tf`) expires old/untagged worker images.
- **CloudWatch Logs** retain `log_retention_days`; the group is owned here so
  `terraform destroy` removes it.
- **Cost alerts** are opt-in: set `monthly_budget_usd` + `budget_alert_emails`.

## Teardown

```sh
terraform destroy
cd bootstrap && terraform destroy -var "state_bucket=petbot-tfstate-<your-account-id>"
```

## CI checks

`.github/workflows/terraform.yml` runs `fmt -check` + `validate` on PRs (no AWS
credentials needed). `.github/workflows/deploy.yml` runs the OIDC build/apply
pipeline above.
