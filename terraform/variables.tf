variable "project" {
  description = "Project name used as a prefix for all resource names."
  type        = string
  default     = "shopmart"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to deploy resources into."
  type        = string
  default     = "ap-southeast-1"
}

variable "alert_email" {
  description = "Email address that receives SNS pipeline alerts."
  type        = string
}

variable "pipeline_schedule" {
  description = "EventBridge Scheduler cron expression for daily pipeline trigger (UTC)."
  type        = string
  # Default: 8:15 AM UTC+7 = 01:15 UTC
  default = "cron(15 1 * * ? *)"
}

variable "glue_worker_type" {
  description = "AWS Glue worker type for the ETL job."
  type        = string
  default     = "G.1X"
}

variable "glue_number_of_workers" {
  description = "Number of Glue workers for the ETL job."
  type        = number
  default     = 2
}

variable "lambda_memory_mb" {
  description = "Memory (MB) allocated to the validation Lambda function."
  type        = number
  default     = 256
}

variable "lambda_timeout_seconds" {
  description = "Timeout (seconds) for the validation Lambda function."
  type        = number
  default     = 300
}

variable "s3_raw_lifecycle_days" {
  description = "Days before raw objects transition to STANDARD_IA storage."
  type        = number
  default     = 30
}

variable "s3_archive_lifecycle_days" {
  description = "Days before archive objects transition to GLACIER storage."
  type        = number
  default     = 90
}

variable "critical_error_rate_threshold" {
  description = "Fraction of bad records that triggers a critical SNS alert (0.0–1.0)."
  type        = number
  default     = 0.2
}

# ---------------------------------------------------------------------------
# Analytics — Athena + QuickSight
# ---------------------------------------------------------------------------

variable "enable_quicksight" {
  description = "Set to true to provision the QuickSight Athena data source. Requires QuickSight to be subscribed in the AWS account first."
  type        = bool
  default     = false
}

variable "quicksight_admin_user" {
  description = "QuickSight username (IAM identity) that will own the Athena data source. Required when enable_quicksight = true."
  type        = string
  default     = ""
}
