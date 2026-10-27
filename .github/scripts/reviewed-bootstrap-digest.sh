#!/usr/bin/env bash
# Usage: reviewed-bootstrap-digest.sh
#
# Prints the digest of the bootstrap plan that the pull request merged as $GITHUB_SHA showed:
# the bootstrap-plan/digest status deploy.yml's bootstrap-plan job posted to its head commit.
# Prints nothing if there is none.
set -euo pipefail

head=$(gh api "repos/$GITHUB_REPOSITORY/commits/$GITHUB_SHA/pulls" \
  | jq -r --arg sha "$GITHUB_SHA" \
    '[.[] | select(.merged_at != null and .merge_commit_sha == $sha)][0].head.sha // empty')
[ -n "$head" ] || exit 0

# Newest first: https://docs.github.com/en/rest/commits/statuses#list-commit-statuses-for-a-reference
gh api "repos/$GITHUB_REPOSITORY/commits/$head/statuses?per_page=100" | jq -r \
  '[.[] | select(.context == "bootstrap-plan/digest" and .creator.login == "github-actions[bot]")][0].description // empty'
