# ---------------------------------------------------------------------------
# Amazon SNS — Pipeline Alert Topic
# Sends success/failure notifications to the BI and Data Engineering teams.
# ---------------------------------------------------------------------------

resource "aws_sns_topic" "pipeline_alerts" {
  name         = local.sns_topic_name
  display_name = "ShopMart Pipeline Alerts"

  # Encrypt SNS messages at rest using the default AWS-managed key
  kms_master_key_id = "alias/aws/sns"
}

resource "aws_sns_topic_subscription" "email_alert" {
  topic_arn = aws_sns_topic.pipeline_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}
