resource "aws_dynamodb_table" "claims" {
  count = local.edge_count

  name         = "${local.edge_name}-claims"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "id"

  attribute {
    name = "id"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }
}
