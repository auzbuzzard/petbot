#!/usr/bin/env bash
# Usage: oidc-claims.sh <workflow-file>
#
# Requests this job's OIDC token for the audience AWS's roles trust, and prints which of the
# claims a trust policy could match it has: true or false only, never the token or a value.
set -euo pipefail

workflow="$1"
if [ -z "${ACTIONS_ID_TOKEN_REQUEST_URL:-}" ] || [ -z "${ACTIONS_ID_TOKEN_REQUEST_TOKEN:-}" ]; then
  echo "::warning::oidc-claims: this job can't request an OIDC token (id-token: write)."
  exit 0
fi

token=$(curl -sSf -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
  "$ACTIONS_ID_TOKEN_REQUEST_URL&audience=sts.amazonaws.com" | jq -r '.value')

payload=$(cut -d. -f2 <<< "$token" | tr '_-' '/+')
while [ $(( ${#payload} % 4 )) -ne 0 ]; do payload="$payload="; done
unset token

result=$(base64 -d <<< "$payload" | jq -r \
  --arg file ".github/workflows/$workflow@" \
  --arg pinned "$GITHUB_REPOSITORY/.github/workflows/$workflow@" \
  --arg repo_id "$GITHUB_REPOSITORY_ID" \
  --arg ref "$GITHUB_REF" '
  [
    "job_workflow_ref present: \(has("job_workflow_ref"))",
    "job_workflow_ref names \($file): \((.job_workflow_ref // "") | contains($file))",
    "job_workflow_ref starts with <repository>/\($file): \((.job_workflow_ref // "") | startswith($pinned))",
    "job_workflow_ref ends with @GITHUB_REF: \((.job_workflow_ref // "") | endswith("@" + $ref))",
    "repository_id present: \(has("repository_id"))",
    "repository_id matches this repository: \(.repository_id == $repo_id)",
    "ref present: \(has("ref"))",
    "ref equals GITHUB_REF: \(.ref == $ref)",
    "ref is refs/heads/main: \(.ref == "refs/heads/main")"
  ] | .[]')

while IFS= read -r line; do echo "oidc-claims: $line"; done <<< "$result"
{
  echo "### OIDC token claims ($workflow, $GITHUB_EVENT_NAME)"
  echo
  sed 's/^/- /' <<< "$result"
} >> "$GITHUB_STEP_SUMMARY"
