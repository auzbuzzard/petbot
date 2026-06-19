# Two deployables share this stack: the core worker (Lambda) and the edge
# (Lightsail container service). Their resource names derive from one prefix so
# the bootstrap deploy role can scope to `${name_prefix}-core*` / `-edge*`.
locals {
  core_name = "${var.name_prefix}-core"
  edge_name = "${var.name_prefix}-edge"
}
