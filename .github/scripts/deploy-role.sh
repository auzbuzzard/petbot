#!/usr/bin/env bash
# Usage: deploy-role.sh <role-name>
#
# Writes DEPLOY_ROLE (the ARN of <role-name> in this account) to $GITHUB_ENV. Each stage's
# deploy role is named in code (bootstrap's var.environments); only the account ID comes
# from the repository's settings, which keep it out of the public code and logs. It is read
# from the job's DEPLOY_ROLE_ARN secret when the environment has one, else from the state
# bucket's name, which ends in the account ID (petbot-tfstate-<account-id>), and is masked
# before anything prints it.
set -euo pipefail

role="$1"
if [[ "${ROLE_ARN_SECRET:-}" =~ ^arn:aws:iam::([0-9]{12}):role/ ]]; then
  account="${BASH_REMATCH[1]}"
elif [[ "${STATE_BUCKET:-}" =~ -([0-9]{12})$ ]]; then
  account="${BASH_REMATCH[1]}"
else
  echo "::error::No account ID: the environment has no DEPLOY_ROLE_ARN secret, and the state bucket's name doesn't end in -<account-id>."
  exit 1
fi
echo "::add-mask::$account"
echo "DEPLOY_ROLE=arn:aws:iam::$account:role/$role" >> "$GITHUB_ENV"
