# --- Message claims: one edge copy handles each Discord message ---------------
#
# Discord delivers every gateway event to every session connected with the bot's
# token. A Lightsail deployment starts the new edge container (which connects to
# the gateway) before it stops the old one, so for a minute or more two copies
# receive every message. Each copy claims the message id here with a conditional
# put before doing anything; only the winner types, invokes the core and answers
# (petbot.platform.dedup). Items expire via TTL, so the table stays tiny;
# on-demand billing makes it ~free at this traffic.

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
