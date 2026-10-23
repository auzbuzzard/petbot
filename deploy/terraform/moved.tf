# The edge's resources are counted (var.edge_enabled), so their unindexed addresses map
# onto instance 0: a stack whose state holds them unindexed keeps them in place.

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
