# PetBot interactions Lambda — Terraform

Infrastructure-as-code for the serverless HTTP-Interactions frontend (epic #28,
issue #30): an AWS Lambda **container image** behind a **Function URL**, with a
least-privilege IAM role. The Function URL output is what #31 sets as Discord's
Interactions Endpoint URL.

```
bootstrap/        one-time encrypted S3 state bucket (local state)
*.tf              the Lambda + ECR + IAM + Function URL stack (S3 remote state)
backend.hcl.example       remote-state backend config (copy -> backend.hcl)
terraform.tfvars.example  inputs (copy -> terraform.tfvars); no secrets here
```

The Lambda image is built from [`../Dockerfile.lambda`](../Dockerfile.lambda).

## Prerequisites

- An AWS account with credentials in your shell (e.g. `aws sso login`).
- Terraform >= 1.11 (for S3-native state locking), Docker, and the AWS CLI.
- Secrets live in **SSM SecureString** parameters, created out-of-band so their
  values never touch Terraform state as managed resources:

  ```sh
  aws ssm put-parameter --type SecureString \
    --name /petbot/interactions/discord_public_key --value "<application public key>"
  # Bot token — used ONLY by the CI command-registration step (register.py),
  # never by the Lambda at request time. Read from SSM in CI; never in GitHub.
  aws ssm put-parameter --type SecureString \
    --name /petbot/interactions/discord_bot_token --value "<bot token>"
  # optional booru auth:
  # aws ssm put-parameter --type SecureString --name /petbot/interactions/derpibooru_api_key --value "..."
  ```

  > Note: the values are injected into the Lambda's environment at apply time, so
  > they do land in Terraform **state**. The state bucket is encrypted, versioned,
  > and private to contain this; fetching SSM at runtime (state stays secret-free)
  > is a documented future hardening (#17).

## One-time: bootstrap remote state

```sh
cd bootstrap
terraform init
terraform apply -var "state_bucket=petbot-tfstate-<your-account-id>"
cd ..
cp backend.hcl.example backend.hcl   # fill in the bucket name
```

The bootstrap stack also creates the **GitHub Actions OIDC provider** and the
**`petbot-github-deploy` IAM role** the CI pipeline assumes (no static AWS keys).
After applying, wire its outputs as repo **variables** (Settings → Secrets and
variables → Actions → Variables — non-secret):

```sh
terraform -chdir=bootstrap output deploy_role_arn   # -> DEPLOY_ROLE_ARN
```

| GitHub Actions variable | Value |
| --- | --- |
| `DEPLOY_ROLE_ARN` | `deploy_role_arn` bootstrap output |
| `AWS_REGION` | e.g. `us-east-1` (match `backend.hcl` / your SSM region) |
| `TF_STATE_BUCKET` | the `state_bucket` you chose above |
| `DISCORD_APP_ID` | your Discord application ID |

## CI deploy (the steady-state path)

`.github/workflows/deploy.yml` does the whole rollout via OIDC — build + push the
arm64 image (tagged with the git SHA), `terraform apply`, then register the slash
commands. **No deploy is ever run from a developer machine.**

- **Roll out to one guild first (instant):** run the workflow via
  *Actions → Deploy → Run workflow* with **`guild_id`** set to your dev/private
  server's ID. `register.py` registers the commands guild-scoped, so they appear
  in that guild immediately and nowhere else.
- **Go global:** a push to `master` runs the same pipeline with an empty
  `guild_id`, registering the commands application-wide (up to ~1h to propagate).
- **First run only:** set Discord's *Interactions Endpoint URL* to the
  `function_url` the workflow prints, and invite the app to the target guild
  (`bot` + `applications.commands` scopes).

## Deploy

Because the function is pinned to the image digest, the image must exist before
the main apply — so it's a two-step the first time:

```sh
cp terraform.tfvars.example terraform.tfvars   # adjust region, SSM names, etc.
terraform init -backend-config=backend.hcl

# 1. Create just the ECR repo.
terraform apply -target=aws_ecr_repository.this

# 2. Build + push the arm64 image to that repo.
REPO=$(terraform output -raw ecr_repository_url)
aws ecr get-login-password | docker login --username AWS --password-stdin "${REPO%/*}"
docker build --platform linux/arm64 -f ../Dockerfile.lambda -t "$REPO:latest" ../..
docker push "$REPO:latest"

# 3. Stand up the function + Function URL.
terraform apply

terraform output function_url   # -> set this as Discord's Interactions Endpoint URL (#31)
```

For subsequent deploys, push a new image (prefer a unique tag, e.g. the git SHA,
set via `-var image_tag=...`) and re-run `terraform apply`.

## Cost & retention

The stack keeps storage bounded and `destroy` complete:

- **ECR lifecycle** (`retention.tf`) expires untagged images after
  `ecr_untagged_expire_days` and keeps only the last `ecr_keep_last_images`.
- **CloudWatch Logs** are an explicit `aws_cloudwatch_log_group` with
  `log_retention_days` retention — so logs don't accumulate forever, and
  `terraform destroy` removes the group (Lambda's auto-created one never expires
  and wouldn't be owned by Terraform).
- **Cost alerts** are opt-in: AWS has no hard spend cap, so set
  `monthly_budget_usd` + `budget_alert_emails` to create an AWS Budget that
  emails you at 80% and 100% of the limit. At PetBot's scale spend is ~$0, so
  this is a smoke alarm, not a throttle.

## Teardown

```sh
terraform destroy
# and, if you want to remove state storage too:
cd bootstrap && terraform destroy -var "state_bucket=petbot-tfstate-<your-account-id>"
```

## CI

`.github/workflows/terraform.yml` runs `fmt -check` + `validate` on PRs (no AWS
credentials needed). `.github/workflows/deploy.yml` runs the full OIDC
build/apply/register pipeline (see **CI deploy** above). The manual two-step
`terraform apply` flow above remains valid for local/break-glass use.
