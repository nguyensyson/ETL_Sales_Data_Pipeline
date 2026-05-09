# ---------------------------------------------------------------------------
# Amazon EventBridge Scheduler — Daily Pipeline Trigger
#
# Fires once daily after the store upload window closes (default 8:15 AM UTC+7
# = 01:15 UTC) and starts the Step Functions state machine.
# ---------------------------------------------------------------------------

resource "aws_scheduler_schedule" "daily_pipeline" {
  name        = local.eventbridge_rule_name
  description = "Triggers the ShopMart sales pipeline daily after the store upload window."
  group_name  = "default"

  # Flexible time window disabled — fire at exactly the scheduled time
  flexible_time_window {
    mode = "OFF"
  }

  schedule_expression          = var.pipeline_schedule
  schedule_expression_timezone = "Asia/Ho_Chi_Minh"

  target {
    arn      = aws_sfn_state_machine.pipeline.arn
    role_arn = aws_iam_role.eventbridge_scheduler.arn

    # Pass today's date as context to the state machine
    input = jsonencode({
      trigger = "scheduled"
      source  = "eventbridge-scheduler"
    })

    retry_policy {
      maximum_retry_attempts       = 2
      maximum_event_age_in_seconds = 3600
    }
  }
}
