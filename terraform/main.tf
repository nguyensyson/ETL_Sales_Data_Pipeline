terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = local.common_tags
  }
}

# ---------------------------------------------------------------------------
# Locals — shared values used across all modules
# ---------------------------------------------------------------------------

locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }

  # S3 bucket names must be globally unique — suffix with account ID
  account_id = data.aws_caller_identity.current.account_id

  bucket_raw       = "${local.name_prefix}-raw-${local.account_id}"
  bucket_stage     = "${local.name_prefix}-stage-${local.account_id}"
  bucket_processed = "${local.name_prefix}-processed-${local.account_id}"
  bucket_errors    = "${local.name_prefix}-errors-${local.account_id}"
  bucket_archive   = "${local.name_prefix}-archive-${local.account_id}"
  bucket_glue      = "${local.name_prefix}-glue-assets-${local.account_id}"

  glue_database_name = "${replace(local.name_prefix, "-", "_")}_catalog"
  glue_job_name      = "${local.name_prefix}-etl-job"
  glue_crawler_raw   = "${local.name_prefix}-crawler-raw"
  glue_crawler_proc  = "${local.name_prefix}-crawler-processed"

  lambda_function_name    = "${local.name_prefix}-csv-validator"
  step_function_name      = "${local.name_prefix}-pipeline"
  eventbridge_rule_name   = "${local.name_prefix}-daily-trigger"
  sns_topic_name          = "${local.name_prefix}-pipeline-alerts"
  cloudwatch_log_group    = "/aws/states/${local.step_function_name}"
}

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
