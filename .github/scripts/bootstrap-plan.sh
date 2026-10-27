#!/usr/bin/env bash
# Usage (from deploy/terraform/bootstrap): bootstrap-plan.sh [terraform plan flags...]
#
# Plans bootstrap (state bootstrap/terraform.tfstate in $TF_VAR_state_bucket) into
# bootstrap.tfplan, printing the full plan, and writes plan.changes (true or false),
# plan.digest (a SHA-256 of the plan's resource changes: the same changes, the same digest)
# and plan.resources (each changed resource's address and actions as a Markdown list, no
# attribute values). deploy.yml's bootstrap-plan job and bootstrap job both plan with it.
set -euo pipefail

terraform init -input=false -no-color \
  -backend-config="bucket=${TF_VAR_state_bucket:?}" \
  -backend-config=key=bootstrap/terraform.tfstate \
  -backend-config="region=${TF_VAR_aws_region:?}" \
  -backend-config=encrypt=true \
  -backend-config=use_lockfile=true

# -detailed-exitcode: 0 = no changes, 2 = changes; anything else is a failure.
set +e
terraform plan -no-color -input=false -detailed-exitcode "$@" -out=bootstrap.tfplan
code=$?
set -e
case "$code" in
  0) echo false > plan.changes ;;
  2) echo true > plan.changes ;;
  *) echo "::error::terraform plan exited $code"; exit 1 ;;
esac

terraform show -json bootstrap.tfplan > plan.json
jq -S '.resource_changes' plan.json | sha256sum | cut -d' ' -f1 > plan.digest
jq -r '(.resource_changes // [])[] | select(.change.actions != ["no-op"])
  | "- `\(.address)`: \(.change.actions | join(", "))"' plan.json > plan.resources
[ -s plan.resources ] || echo "No changes." > plan.resources
rm plan.json
