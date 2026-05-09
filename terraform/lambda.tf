# ---------------------------------------------------------------------------
# Lambda — CSV Validation Function
# Validates schema and data quality; routes files to stage or error bucket.
# ---------------------------------------------------------------------------

# Package the Lambda source code into a zip archive
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../src/lambda"
  output_path = "${path.module}/../.build/lambda_validator.zip"
}

resource "aws_lambda_function" "csv_validator" {
  function_name = local.lambda_function_name
  description   = "Validates CSV sales files and routes them to stage or error bucket."

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"

  role        = aws_iam_role.lambda_exec.arn
  memory_size = var.lambda_memory_mb
  timeout     = var.lambda_timeout_seconds

  environment {
    variables = {
      RAW_BUCKET                     = aws_s3_bucket.raw.bucket
      STAGE_BUCKET                   = aws_s3_bucket.stage.bucket
      ERROR_BUCKET                   = aws_s3_bucket.errors.bucket
      SNS_TOPIC_ARN                  = aws_sns_topic.pipeline_alerts.arn
      CRITICAL_ERROR_RATE_THRESHOLD  = tostring(var.critical_error_rate_threshold)
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_logs,
    aws_cloudwatch_log_group.lambda,
  ]
}

resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${local.lambda_function_name}"
  retention_in_days = 30
}
