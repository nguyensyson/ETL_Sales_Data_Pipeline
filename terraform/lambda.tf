# ---------------------------------------------------------------------------
# Lambda — CSV Validation Function
# Validates schema and data quality; routes files to stage or error bucket.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Lambda Layer — pandas (pre-built for linux/x86_64)
# Run build_layer.ps1 from the repo root before terraform apply.
# ---------------------------------------------------------------------------

locals {
  layer_build_dir = "${path.module}/../.build/layer"
  layer_zip_path  = "${path.module}/../.build/lambda_layer_pandas.zip"
}

data "archive_file" "lambda_layer_zip" {
  type        = "zip"
  source_dir  = local.layer_build_dir
  output_path = local.layer_zip_path
}

resource "aws_lambda_layer_version" "pandas_layer" {
  layer_name          = "${local.name_prefix}-pandas"
  description         = "pandas 2.2.2 for python3.12"
  filename            = data.archive_file.lambda_layer_zip.output_path
  source_code_hash    = data.archive_file.lambda_layer_zip.output_base64sha256
  compatible_runtimes = ["python3.12"]
}

# ---------------------------------------------------------------------------
# Package the Lambda source code into a zip archive
# ---------------------------------------------------------------------------

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

  layers = [aws_lambda_layer_version.pandas_layer.arn]

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
