# --- Request claims: one answer per Discord message ---------------------------
#
# Discord delivers every gateway event to every session connected with the bot's
# token, so two edge copies (a Lightsail deployment rolling over, or any second copy
# of the token) would each answer the same message. The core claims each message id
# here with a conditional put before answering; a later delivery of the same id gets
# an empty result (petbot.platform.dedup). Items expire via TTL, so the table stays
# tiny; on-demand billing makes it ~free at this traffic.

resource "aws_dynamodb_table" "claims" {
  name         = "${local.core_name}-claims"
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

resource "aws_iam_role_policy" "claims" {
  name = "${local.core_name}-claims"
  role = aws_iam_role.lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "dynamodb:PutItem"
      Resource = aws_dynamodb_table.claims.arn
    }]
  })
}
