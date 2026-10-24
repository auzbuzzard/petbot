#!/usr/bin/env bash
# Usage (from deploy/terraform, initialised on the legacy state): legacy-plan.sh
#
# Plans the legacy stack into legacy.tfplan, the same way for legacy.yml's plan job and its
# apply job: a destroy when stages/legacy.tfvars sets `retired`, else a plan of the edge's
# resources only (its service's pause is the change). Writes RETIRED and DIGEST (a hash of
# the plan's resource changes, which the apply job compares to the reviewed plan's) to
# $GITHUB_ENV, and the digest to $GITHUB_OUTPUT.
set -euo pipefail

# The edge's resources: the `to` addresses of moved.tf, since Terraform records a move only
# for a resource the targeted plan includes, and the edge's one counted data source
# (secrets.tf), which its state also holds unindexed and so moves the same way.
targets=(
  aws_lightsail_container_service.edge
  aws_ecr_repository.edge
  aws_ecr_repository_policy.edge
  aws_iam_user.edge
  time_rotating.edge_key
  aws_iam_access_key.edge
  aws_iam_user_policy.edge_invoke
  aws_iam_user_policy.edge_secrets
  aws_dynamodb_table.claims
  aws_ecr_lifecycle_policy.edge
  data.aws_iam_policy_document.edge_secrets
)

retired=$(echo 'var.retired' | terraform console)

# The function is pinned to an image digest that its plan reads back, so the plan uses the
# newest tag in the stack's registry, which is what it runs.
tag=$(aws ecr describe-images --repository-name petbot-core \
  --query 'sort_by(imageDetails, &imagePushedAt)[-1].imageTags[0]' --output text)
export TF_VAR_image_tag="$tag" TF_VAR_edge_image_tag="$tag"

args=(-input=false -lock-timeout=120s -out=legacy.tfplan)
if [ "$retired" = true ]; then
  args+=(-destroy)
else
  for target in "${targets[@]}"; do
    args+=("-target=$target")
  done
fi

# The log is public: redact access key ids (the edge's key is one of these resources).
terraform plan "${args[@]}" 2>&1 | sed -u -E 's/(AKIA|ASIA)[A-Z0-9]{16}/\1****************/g'

digest=$(terraform show -json legacy.tfplan | jq -S '.resource_changes' | sha256sum | cut -d' ' -f1)
{
  echo "RETIRED=$retired"
  echo "DIGEST=$digest"
} >> "$GITHUB_ENV"
echo "digest=$digest" >> "$GITHUB_OUTPUT"
