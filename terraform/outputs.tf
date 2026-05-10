# ---------------------------------------------------------------------------
# Outputs — useful values after terraform apply
# ---------------------------------------------------------------------------

output "s3_raw_bucket" {
  description = "Name of the S3 raw ingestion bucket."
  value       = aws_s3_bucket.raw.bucket
}

output "s3_stage_bucket" {
  description = "Name of the S3 staging bucket."
  value       = aws_s3_bucket.stage.bucket
}

output "s3_processed_bucket" {
  description = "Name of the S3 processed (Parquet) bucket."
  value       = aws_s3_bucket.processed.bucket
}

output "s3_errors_bucket" {
  description = "Name of the S3 errors bucket."
  value       = aws_s3_bucket.errors.bucket
}

output "s3_archive_bucket" {
  description = "Name of the S3 archive bucket."
  value       = aws_s3_bucket.archive.bucket
}

output "lambda_function_name" {
  description = "Name of the CSV validation Lambda function."
  value       = aws_lambda_function.csv_validator.function_name
}

output "glue_job_name" {
  description = "Name of the Glue ETL job."
  value       = aws_glue_job.etl.name
}

output "step_function_arn" {
  description = "ARN of the Step Functions state machine."
  value       = aws_sfn_state_machine.pipeline.arn
}

output "sns_topic_arn" {
  description = "ARN of the SNS pipeline alerts topic."
  value       = aws_sns_topic.pipeline_alerts.arn
}

output "glue_catalog_database" {
  description = "Name of the Glue Data Catalog database."
  value       = aws_glue_catalog_database.main.name
}

output "athena_workgroup" {
  description = "Name of the Athena workgroup for pipeline analytics queries."
  value       = aws_athena_workgroup.main.name
}

output "athena_results_bucket" {
  description = "S3 bucket where Athena query results are stored."
  value       = aws_s3_bucket.athena_results.bucket
}

output "quicksight_role_arn" {
  description = "IAM role ARN to assign to QuickSight for Athena access."
  value       = aws_iam_role.quicksight.arn
}
