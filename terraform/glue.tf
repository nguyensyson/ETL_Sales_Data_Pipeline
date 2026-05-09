# ---------------------------------------------------------------------------
# AWS Glue — Database, ETL Job, and Crawlers
# ---------------------------------------------------------------------------

# ── Glue Data Catalog database ───────────────────────────────────────────────

resource "aws_glue_catalog_database" "main" {
  name        = local.glue_database_name
  description = "ShopMart sales pipeline catalog — raw and processed schemas."
}

# ── Upload Glue ETL script to S3 ─────────────────────────────────────────────

resource "aws_s3_object" "glue_script" {
  bucket = aws_s3_bucket.glue_assets.bucket
  key    = "scripts/glue_etl_job.py"
  source = "${path.module}/../src/glue/glue_etl_job.py"
  etag   = filemd5("${path.module}/../src/glue/glue_etl_job.py")
}

# ── Glue ETL Job ─────────────────────────────────────────────────────────────

resource "aws_glue_job" "etl" {
  name        = local.glue_job_name
  description = "Transforms staged CSV sales data to partitioned Parquet in the processed bucket."
  role_arn    = aws_iam_role.glue.arn

  glue_version      = "4.0"
  worker_type       = var.glue_worker_type
  number_of_workers = var.glue_number_of_workers

  command {
    name            = "glueetl"
    script_location = "s3://${aws_s3_bucket.glue_assets.bucket}/scripts/glue_etl_job.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-enable"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-spark-ui"                  = "false"
    "--TempDir"                          = "s3://${aws_s3_bucket.glue_assets.bucket}/temp/"
    "--STAGE_BUCKET"                     = aws_s3_bucket.stage.bucket
    "--PROCESSED_BUCKET"                 = aws_s3_bucket.processed.bucket
    "--ERROR_BUCKET"                     = aws_s3_bucket.errors.bucket
  }

  execution_property {
    max_concurrent_runs = 1
  }

  # Retry up to 2 times on transient failures (BR-8)
  max_retries = 2

  depends_on = [aws_s3_object.glue_script]
}

# ── Glue Crawler — raw / staged data ─────────────────────────────────────────

resource "aws_glue_crawler" "raw" {
  name          = local.glue_crawler_raw
  database_name = aws_glue_catalog_database.main.name
  role          = aws_iam_role.glue.arn
  description   = "Crawls the stage bucket to register raw CSV schema."

  s3_target {
    path = "s3://${aws_s3_bucket.stage.bucket}/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })
}

# ── Glue Crawler — processed / Parquet data ───────────────────────────────────

resource "aws_glue_crawler" "processed" {
  name          = local.glue_crawler_proc
  database_name = aws_glue_catalog_database.main.name
  role          = aws_iam_role.glue.arn
  description   = "Crawls the processed bucket to register Parquet schema for Athena."

  s3_target {
    path = "s3://${aws_s3_bucket.processed.bucket}/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version = 1.0
    CrawlerOutput = {
      Partitions = { AddOrUpdateBehavior = "InheritFromTable" }
    }
  })
}
