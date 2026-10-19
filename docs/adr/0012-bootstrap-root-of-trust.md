# ADR 0012: Bootstrap as the root of trust: remote state, name-scoped deploy role

- Status: Accepted
- Date: 2026-10-19

## Context

`deploy/terraform/bootstrap` creates what CI cannot create for itself: the S3 state
bucket, the GitHub Actions OIDC provider and the `petbot-github-deploy` role CI assumes.
Two of its choices made every infrastructure addition a manual ordeal:

- **Local state.** Bootstrap kept its own state as a local file on whichever machine first
  applied it. That file was not kept, so nobody could plan or apply bootstrap any more
  without importing everything first.
- **ARN-pinned permissions.** The deploy role's policy listed the exact ARNs of the
  resources that existed (`petbot-core`, `petbot-edge`, `petbot-core-role`, …). Any new
  resource, such as a DynamoDB table, needed a bootstrap change and an admin apply before
  its PR could deploy.

## Decision

- Bootstrap stays an **admin-applied root of trust**. CI never applies it, so CI can
  never widen its own permissions. This is the standard bootstrap pattern; "baseline" (an
  account-wide guardrail layer such as Control Tower's) is a different, org-level concept
  this single-account project doesn't need.
- Bootstrap's state is **remote**, in the bucket it manages (`bootstrap/terraform.tfstate`,
  native S3 locking). A new account creates the bucket first and imports it.
- The deploy role is **scoped by naming convention**: it may manage resources named
  `<name_prefix>-*` (ECR repositories, Lambda functions and their log groups, DynamoDB
  tables, IAM roles and users, PassRole to Lambda only), plus account-wide calls that
  have no resource form (ECR login, log-group listing, Lightsail). An explicit deny on
  `role/<name_prefix>-github-*` keeps it from editing the CI roles (and, since the
  operator role was added, `role/<name_prefix>-operator`).
- Name scoping alone would still let CI create a `petbot-*` user or role with an admin
  policy. So bootstrap also owns a **permissions boundary**,
  `<name_prefix>-workload-boundary` (no IAM; logs, telemetry, model invocation and
  data-plane access to `petbot-*` resources), and the deploy role may create or edit
  IAM principals only with it attached (`iam:PermissionsBoundary`). CI can write any
  workload policy; the boundary caps what it grants. The deploy role may read and
  write only the root stack's state (`petbot/*`), not bootstrap's.

## Consequences

- Adding resources to the root stack needs no bootstrap change; only a new AWS service
  does, and then the PR edits `bootstrap/main.tf` and an admin applies it before merging.
- The blast radius of a stolen CI token grows from "the resources that exist today" to
  "any resource named `petbot-*` of the listed services". The trust policy still lets any
  ref of this repo assume the role, as it did before; tightening that to `master` is a
  separate decision.
- A workload needing a permission outside the boundary is a bootstrap change, as is
  a new service.
- The `petbot-*` prefix is reserved for the stack. The hand-made Bedrock API-key user
  `petbot-bedrock-key` falls inside the deploy role's user scope; CI gains nothing from
  that, since it already reads that user's key from SSM.
- Adopting the existing account: the seven bootstrap resources were imported into the
  remote state; the changes applied were the deploy role's policy and the new boundary.

## Follow-on: operator access (2026-10)

Triage (reading the edge's container logs, the Lambda's logs, the claims table) and
integration tests (invoking the core) had been done outside IaC: the `claude` IAM user
sat in a hand-made `claude-automation` group with AWS's `ReadOnlyAccess` (plus a deny on
two SSM secrets), and gained Lightsail logs and Lambda invoke from hand-attached inline
policies. `ReadOnlyAccess` also reads the state bucket, i.e. every secret Terraform
injected, so the SSM deny protected nothing. Bootstrap now owns that access too:
`petbot-operator`, a read-only role plus `lambda:InvokeFunction` on the core, assumed
by the `claude` user, whose only permission is that `sts:AssumeRole`. It sits in
bootstrap, not the root stack, because who may access the account belongs to the root
of trust; CI is denied it like its own role. Secrets (SSM, Terraform state) and every
write stay out of it; elevated changes are an admin's. The group is removed, so the
user holds nothing but the `sts:AssumeRole`. The cost: the operator can no longer plan
bootstrap (it reads neither bootstrap's state nor the IAM it would diff), which is the
point; an admin plans and applies it.
