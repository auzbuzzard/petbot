# Map the edge's unindexed resource addresses onto instance 0 of the counted edge
# (var.edge_enabled). A state that holds them unindexed (the legacy stack's) has them
# moved in place, which lets legacy.yml pause and destroy that stack with this code; a
# state without them has nothing to move. .github/scripts/legacy-plan.sh targets these addresses, and the counted data source
# data.aws_iam_policy_document.edge_secrets, which moves the same way.

moved {
  from = aws_lightsail_container_service.edge
  to   = aws_lightsail_container_service.edge[0]
}

moved {
  from = aws_ecr_repository.edge
  to   = aws_ecr_repository.edge[0]
}

moved {
  from = aws_ecr_repository_policy.edge
  to   = aws_ecr_repository_policy.edge[0]
}

moved {
  from = aws_iam_user.edge
  to   = aws_iam_user.edge[0]
}

moved {
  from = time_rotating.edge_key
  to   = time_rotating.edge_key[0]
}

moved {
  from = aws_iam_access_key.edge
  to   = aws_iam_access_key.edge[0]
}

moved {
  from = aws_iam_user_policy.edge_invoke
  to   = aws_iam_user_policy.edge_invoke[0]
}

moved {
  from = aws_iam_user_policy.edge_secrets
  to   = aws_iam_user_policy.edge_secrets[0]
}

moved {
  from = aws_dynamodb_table.claims
  to   = aws_dynamodb_table.claims[0]
}

moved {
  from = aws_ecr_lifecycle_policy.edge
  to   = aws_ecr_lifecycle_policy.edge[0]
}
