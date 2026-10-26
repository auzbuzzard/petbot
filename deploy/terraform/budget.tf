resource "aws_budgets_budget" "monthly" {
  count = var.monthly_budget_usd > 0 && length(var.budget_alert_emails) > 0 ? 1 : 0

  name         = "${var.name_prefix}-monthly"
  budget_type  = "COST"
  time_unit    = "MONTHLY"
  limit_amount = tostring(var.monthly_budget_usd)
  limit_unit   = "USD"

  dynamic "notification" {
    for_each = toset([80, 100])
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "PERCENTAGE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = var.budget_alert_emails
    }
  }
}
