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

## Teardown

```sh
terraform destroy
# and, if you want to remove state storage too:
cd bootstrap && terraform destroy -var "state_bucket=petbot-tfstate-<your-account-id>"
```

## CI

`.github/workflows/terraform.yml` runs `fmt -check` + `validate` on PRs (no AWS
credentials needed). `plan`/`apply` are run manually from here for now; a full
OIDC pipeline can be added later.
