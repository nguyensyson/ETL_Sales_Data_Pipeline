# ---------------------------------------------------------------------------
# CloudWatch — Alarms and Dashboards for pipeline observability
# ---------------------------------------------------------------------------

# ── Alarm: Step Functions execution failures ─────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "sfn_failures" {
  alarm_name          = "${local.name_prefix}-sfn-execution-failures"
  alarm_description   = "Fires when the pipeline Step Functions execution fails."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.pipeline.arn
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
  ok_actions    = [aws_sns_topic.pipeline_alerts.arn]
}

# ── Alarm: No pipeline executions started (missed trigger) ───────────────────

resource "aws_cloudwatch_metric_alarm" "sfn_no_executions" {
  alarm_name          = "${local.name_prefix}-sfn-no-executions"
  alarm_description   = "Fires when no Step Functions execution starts within the expected daily window — possible EventBridge trigger failure."
  comparison_operator = "LessThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsStarted"
  namespace           = "AWS/States"
  period              = 7200 # 2-hour window after scheduled trigger
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "breaching"

  dimensions = {
    StateMachineArn = aws_sfn_state_machine.pipeline.arn
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
}

# ── Alarm: Lambda validation errors ──────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "lambda_errors" {
  alarm_name          = "${local.name_prefix}-lambda-validation-errors"
  alarm_description   = "Fires when the CSV validation Lambda function throws errors."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.csv_validator.function_name
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
}

# ── Alarm: Glue ETL job failures ─────────────────────────────────────────────

resource "aws_cloudwatch_metric_alarm" "glue_job_failures" {
  alarm_name          = "${local.name_prefix}-glue-job-failures"
  alarm_description   = "Fires when the Glue ETL job fails after all retries."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "glue.driver.aggregate.numFailedTasks"
  namespace           = "Glue"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  treat_missing_data  = "notBreaching"

  dimensions = {
    JobName = aws_glue_job.etl.name
    Type    = "gauge"
  }

  alarm_actions = [aws_sns_topic.pipeline_alerts.arn]
}

# ── CloudWatch Log Groups (referenced by other resources) ────────────────────
# Lambda and Step Functions log groups are defined in lambda.tf and
# stepfunctions.tf respectively to keep resources co-located.
