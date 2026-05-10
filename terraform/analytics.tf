# ---------------------------------------------------------------------------
# Analytics Layer — Amazon Athena + Amazon QuickSight
#
# Athena queries the processed Parquet data in S3 via the Glue Data Catalog.
# QuickSight connects to Athena as a data source for BI dashboards.
# ---------------------------------------------------------------------------

# ── S3 bucket for Athena query results ──────────────────────────────────────

resource "aws_s3_bucket" "athena_results" {
  bucket = "${local.name_prefix}-athena-results-${local.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Bucket policy — allow QuickSight service principal to verify/access the bucket
# QuickSight runs a connection test using its own service role, not the IAM role
# defined below, so the bucket must explicitly grant access to the service.
resource "aws_s3_bucket_policy" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowQuickSightServiceAccess"
        Effect = "Allow"
        Principal = {
          Service = "quicksight.amazonaws.com"
        }
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts"
        ]
        Resource = [
          aws_s3_bucket.athena_results.arn,
          "${aws_s3_bucket.athena_results.arn}/*"
        ]
        Condition = {
          StringEquals = {
            "aws:SourceAccount" = local.account_id
          }
        }
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.athena_results]
}

# Auto-expire query result files after 30 days to control storage costs
resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    filter { prefix = "" }
    expiration {
      days = 30
    }
  }
}

# ── Athena Workgroup ─────────────────────────────────────────────────────────

resource "aws_athena_workgroup" "main" {
  name        = "${local.name_prefix}-workgroup"
  description = "ShopMart sales analytics workgroup — queries processed Parquet data."

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.athena_results.bucket}/query-results/"

      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }

    # Limit query cost — reject queries that would scan more than 1 GB
    bytes_scanned_cutoff_per_query = 1073741824
  }
}

# ── Athena Named Queries — pre-built analytics queries ──────────────────────

resource "aws_athena_named_query" "daily_revenue" {
  name      = "${local.name_prefix}-daily-revenue"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name

  description = "Total revenue per day across all stores."

  query = <<-SQL
    SELECT
      order_date,
      SUM(line_revenue)                          AS total_revenue,
      COUNT(DISTINCT order_id)                   AS total_orders,
      COUNT(DISTINCT customer_id)                AS unique_customers
    FROM "${aws_glue_catalog_database.main.name}"."processed"
    GROUP BY order_date
    ORDER BY order_date DESC;
  SQL
}

resource "aws_athena_named_query" "top_products" {
  name      = "${local.name_prefix}-top-products"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name

  description = "Top 20 products by total revenue."

  query = <<-SQL
    SELECT
      product_id,
      SUM(quantity)                              AS total_units_sold,
      SUM(line_revenue)                          AS total_revenue,
      COUNT(DISTINCT order_id)                   AS order_count
    FROM "${aws_glue_catalog_database.main.name}"."processed"
    GROUP BY product_id
    ORDER BY total_revenue DESC
    LIMIT 20;
  SQL
}

resource "aws_athena_named_query" "payment_success_rate" {
  name      = "${local.name_prefix}-payment-success-rate"
  workgroup = aws_athena_workgroup.main.id
  database  = aws_glue_catalog_database.main.name

  description = "Daily payment success rate across all stores."

  query = <<-SQL
    SELECT
      order_date,
      COUNT(order_id)                                                    AS total_orders,
      SUM(CASE WHEN payment_status = 'paid' THEN 1 ELSE 0 END)          AS paid_orders,
      ROUND(
        SUM(CASE WHEN payment_status = 'paid' THEN 1.0 ELSE 0 END)
        / COUNT(order_id) * 100, 2
      )                                                                  AS success_rate_pct
    FROM "${aws_glue_catalog_database.main.name}"."processed"
    GROUP BY order_date
    ORDER BY order_date DESC;
  SQL
}

# ── IAM — Athena + S3 access for QuickSight ──────────────────────────────────

resource "aws_iam_role" "quicksight" {
  name        = "${local.name_prefix}-quicksight-role"
  description = "Allows QuickSight to query Athena and read processed S3 data."

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "quicksight.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "quicksight_athena" {
  name = "${local.name_prefix}-quicksight-athena-policy"
  role = aws_iam_role.quicksight.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # Athena — run queries and read results
        Effect = "Allow"
        Action = [
          "athena:BatchGetQueryExecution",
          "athena:GetQueryExecution",
          "athena:GetQueryResults",
          "athena:GetQueryResultsStream",
          "athena:ListQueryExecutions",
          "athena:StartQueryExecution",
          "athena:StopQueryExecution",
          "athena:GetWorkGroup",
          "athena:GetDataCatalog",
          "athena:ListDatabases",
          "athena:ListTableMetadata",
          "athena:GetTableMetadata"
        ]
        Resource = "*"
      },
      {
        # S3 — read processed Parquet data and write/read query results
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.processed.arn,
          "${aws_s3_bucket.processed.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          aws_s3_bucket.athena_results.arn,
          "${aws_s3_bucket.athena_results.arn}/*"
        ]
      },
      {
        # Glue Data Catalog — read schema metadata
        Effect = "Allow"
        Action = [
          "glue:GetDatabase",
          "glue:GetDatabases",
          "glue:GetTable",
          "glue:GetTables",
          "glue:GetPartition",
          "glue:GetPartitions",
          "glue:BatchGetPartition"
        ]
        Resource = [
          "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${local.account_id}:catalog",
          "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${local.account_id}:database/${local.glue_database_name}",
          "arn:${data.aws_partition.current.partition}:glue:${var.aws_region}:${local.account_id}:table/${local.glue_database_name}/*"
        ]
      }
    ]
  })
}

# ── QuickSight Data Source (Athena) ──────────────────────────────────────────
#
# NOTE: aws_quicksight_data_source requires:
#   1. A QuickSight account already subscribed in the AWS account.
#   2. The var.quicksight_account_id to be set (same as AWS account ID
#      unless using a separate QuickSight namespace).
#
# If QuickSight is not yet subscribed, this resource can be commented out
# and the data source created manually in the QuickSight console after
# running terraform apply for the rest of the infrastructure.
# ---------------------------------------------------------------------------

resource "aws_quicksight_data_source" "athena" {
  count = var.enable_quicksight ? 1 : 0

  aws_account_id = local.account_id
  data_source_id = "${local.name_prefix}-athena-datasource"
  name           = "ShopMart Sales Pipeline (Athena)"
  type           = "ATHENA"

  parameters {
    athena {
      work_group = aws_athena_workgroup.main.name
    }
  }

  permission {
    actions = [
      "quicksight:DescribeDataSource",
      "quicksight:DescribeDataSourcePermissions",
      "quicksight:PassDataSource",
      "quicksight:UpdateDataSource",
      "quicksight:DeleteDataSource",
      "quicksight:UpdateDataSourcePermissions"
    ]
    principal = "arn:${data.aws_partition.current.partition}:quicksight:${var.aws_region}:${local.account_id}:user/default/${var.quicksight_admin_user}"
  }

  ssl_properties {
    disable_ssl = false
  }

  depends_on = [
    aws_athena_workgroup.main,
    aws_s3_bucket_policy.athena_results,
    aws_iam_role_policy.quicksight_athena
  ]
}
