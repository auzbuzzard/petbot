#!/usr/bin/env bash
# Usage (from the repository root): check-stage-files.sh
#
# Checks each deploy/terraform/stages/<stage>.tfvars as the pipelines use it. Every setting
# must be a variable of the root stack: Terraform only warns about an undeclared one, so a
# misspelt setting would fall back to its default unnoticed (edge_enabled's is true). Then
# the file is planned offline with its stage's name_prefix (tests/stages, mocked providers).
set -euo pipefail
cd deploy/terraform

declared=$(sed -nE 's/^variable "([a-z0-9_]+)".*/\1/p' ./*.tf | sort -u)
status=0
for file in stages/*.tfvars; do
  # Top-level settings start a line; map entries and list items are indented.
  for name in $(sed -nE 's/^([a-z0-9_]+)[[:space:]]*=.*/\1/p' "$file"); do
    if ! grep -qx "$name" <<< "$declared"; then
      echo "::error file=deploy/terraform/$file::$name is not a variable of the root stack"
      status=1
    fi
  done
done
[ "$status" = 0 ] || exit 1

for file in stages/*.tfvars; do
  stage=$(basename "$file" .tfvars)
  prefix="petbot-$stage"
  if [ "$stage" = legacy ]; then prefix=petbot; fi
  echo "--- $file (name_prefix $prefix)"
  terraform test -no-color -test-directory=tests/stages -var-file="$file" -var="name_prefix=$prefix"
done
