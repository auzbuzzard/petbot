# ADR 0012: Bootstrap as the root of trust: remote state, scoped CI roles, gated pipeline

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

- Bootstrap is the **root of trust**, applied by its own **gated pipeline**
  (`bootstrap.yml`), never by the deploy pipeline. An admin applies it by hand once, to
  seed an account; after that a change is a PR, planned on merge with a read-only role
  and applied only after a required reviewer approves the `bootstrap` environment. (As
  first accepted, bootstrap was admin-applied on every change; see the follow-on below.)
  "Baseline" (an account-wide guardrail layer such as Control Tower's) is a different,
  org-level concept this single-account project doesn't need.
- **Every OIDC role trusts exactly one GitHub environment** (`sub` =
  `repo:<repo>:environment:<name>`), and each environment admits only `main`:
  `production` for the deploy role, `bootstrap-plan` and `bootstrap` for the pipeline.
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
  does, and that bootstrap change lands (and is approved and applied) first.
- The blast radius of a stolen deploy token grows from "the resources that exist today"
  to "any resource named `petbot-*` of the listed services"; getting such a token needs a
  job running in `production` on `main`, approved by its required reviewer. Every
  deploy therefore waits on that approval: a merge alone ships nothing.
- A workload needing a permission outside the boundary is a bootstrap change, as is
  a new service.
- The `petbot-*` prefix is reserved for the stack. The hand-made Bedrock API-key user
  `petbot-bedrock-key` falls inside the deploy role's user scope; CI gains nothing from
  that, since it already reads that user's key from SSM.
- Adopting the existing account: the seven bootstrap resources were imported into the
  remote state; the changes applied were the deploy role's policy and the new boundary.
- The GitHub environments' branch rules and required reviewer are part of the trust
  model but live in GitHub settings, not Terraform: managing them as code would need a
  long-lived GitHub admin credential in CI, a larger risk than three settings an admin
  sets once (README "Bootstrap").

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
write stay out of it; access changes go through the bootstrap pipeline. The group is
removed, so the user holds nothing but the `sts:AssumeRole`.

## Follow-on: one trust model, bootstrap applied by a gated pipeline (2026-10)

An audit of the CI trust found:

- The deploy role trusted `repo:auzbuzzard/petbot:*`: any job in any workflow of the
  repo, on any branch or pull request, could assume it. That includes the two AI
  workflows (`claude.yml`, `claude-code-review.yml`), which hold `id-token: write`, run
  on PR and comment events, and act on text anyone can write. A prompt-injected agent,
  or a pushed branch with its own workflow, could deploy code and read the stack's
  secrets.
- Bootstrap was applied by hand on every change, so the root of trust was the one part
  of the infrastructure outside GitOps.

Decision:

- Each OIDC role trusts one environment's `sub` exactly (`StringEquals`), and each
  environment's deployment-branch rule admits only `main`. A job can only get a role
  by running on `main` in that environment.
- Bootstrap gets its own two roles: plan (read-only, plus the state lock) and apply
  (scoped to what bootstrap manages, no deleting the state bucket, no minting the
  operator's credentials). Apply runs only the plan the reviewer saw, and only after
  the `bootstrap` environment's required reviewer approves. The apply role can edit
  itself, so it is exactly as strong as that approval, which is why only it, never the
  deploy role, may touch the access roles.
- The state bucket refuses plain HTTP and is `prevent_destroy`.
- The workflows that hold AWS credentials pin their actions to commit SHAs.

The only manual step left is seeding a new account.
