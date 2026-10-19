# Two deployables share this stack: the core worker (Lambda) and the edge
# (Lightsail container service). Their resource names derive from one prefix so
# the bootstrap deploy role can scope to `${name_prefix}-*`.
locals {
  core_name = "${var.name_prefix}-core"
  edge_name = "${var.name_prefix}-edge"

  # Created by bootstrap. The deploy role may create IAM roles and users only with
  # this permissions boundary attached, so every principal here carries it.
  workload_boundary_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.name_prefix}-workload-boundary"
}
