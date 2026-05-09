"""
AWS Glue ETL Job — Sales Data Transformation (Step 7 in architecture diagram).

Reads staged CSV files from S3, applies the full transformation pipeline,
writes clean Parquet output partitioned by year/month/day, and writes
rejected records to the error bucket.

Job parameters (passed via --job-arguments or Glue default_arguments):
  --STAGE_BUCKET     : Source bucket containing staged CSV files
  --PROCESSED_BUCKET : Destination bucket for Parquet output
  --ERROR_BUCKET     : Destination bucket for rejected records
"""

import sys
import logging
from datetime import datetime

from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, IntegerType

# ---------------------------------------------------------------------------
# Initialise Glue context
# ---------------------------------------------------------------------------

args = getResolvedOptions(
    sys.argv,
    ["JOB_NAME", "STAGE_BUCKET", "PROCESSED_BUCKET", "ERROR_BUCKET"],
)

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args["JOB_NAME"], args)

logger = logging.getLogger()
logger.setLevel(logging.INFO)

STAGE_BUCKET = args["STAGE_BUCKET"]
PROCESSED_BUCKET = args["PROCESSED_BUCKET"]
ERROR_BUCKET = args["ERROR_BUCKET"]

REQUIRED_COLUMNS = [
    "order_id", "customer_id", "product_id",
    "order_date", "quantity", "unit_price", "payment_status",
]
VALID_PAYMENT_STATUSES = {"paid", "pending", "failed"}

# ---------------------------------------------------------------------------
# 1. Read staged CSV files
# ---------------------------------------------------------------------------

logger.info("Reading staged CSV files from s3://%s/staged/", STAGE_BUCKET)

df = spark.read.option("header", "true").csv(
    f"s3://{STAGE_BUCKET}/staged/"
)

total_records = df.count()
logger.info("Total records loaded: %d", total_records)

# ---------------------------------------------------------------------------
# 2. Cast numeric columns
# ---------------------------------------------------------------------------

df = (
    df
    .withColumn("quantity", df["quantity"].cast(DoubleType()))
    .withColumn("unit_price", df["unit_price"].cast(DoubleType()))
)

# ---------------------------------------------------------------------------
# 3. Separate valid and invalid rows
# ---------------------------------------------------------------------------

valid_condition = (
    F.col("order_id").isNotNull()
    & F.col("customer_id").isNotNull() & (F.trim(F.col("customer_id")) != "")
    & F.col("product_id").isNotNull()
    & F.col("quantity").isNotNull() & (F.col("quantity") > 0)
    & F.col("unit_price").isNotNull() & (F.col("unit_price") >= 0)
    & F.col("payment_status").isin(list(VALID_PAYMENT_STATUSES))
)

valid_df = df.filter(valid_condition)
invalid_df = df.filter(~valid_condition)

valid_count = valid_df.count()
invalid_count = invalid_df.count()
logger.info("Valid: %d | Invalid: %d", valid_count, invalid_count)

# ---------------------------------------------------------------------------
# 4. Write invalid records to error bucket
# ---------------------------------------------------------------------------

if invalid_count > 0:
    run_date = datetime.utcnow().strftime("%Y%m%d")
    invalid_df.write.mode("append").option("header", "true").csv(
        f"s3://{ERROR_BUCKET}/glue-errors/{run_date}/"
    )
    logger.info("Invalid records written to s3://%s/glue-errors/%s/", ERROR_BUCKET, run_date)

# ---------------------------------------------------------------------------
# 5. Remove duplicates
# ---------------------------------------------------------------------------

valid_df = valid_df.dropDuplicates(["order_id"])
dedup_count = valid_df.count()
logger.info("After dedup: %d rows (removed %d duplicates)", dedup_count, valid_count - dedup_count)

# ---------------------------------------------------------------------------
# 6. Compute line_revenue and partition columns
# ---------------------------------------------------------------------------

valid_df = (
    valid_df
    .withColumn("line_revenue", F.col("quantity") * F.col("unit_price"))
    .withColumn("order_date_parsed", F.to_date(F.col("order_date"), "yyyy-MM-dd"))
    .withColumn("year", F.year("order_date_parsed").cast(IntegerType()))
    .withColumn("month", F.month("order_date_parsed").cast(IntegerType()))
    .withColumn("day", F.dayofmonth("order_date_parsed").cast(IntegerType()))
    .drop("order_date_parsed")
)

# ---------------------------------------------------------------------------
# 7. Write processed Parquet — partitioned by year/month/day
# ---------------------------------------------------------------------------

logger.info("Writing Parquet to s3://%s/ (partitioned by year/month/day)", PROCESSED_BUCKET)

valid_df.write.mode("append").partitionBy("year", "month", "day").parquet(
    f"s3://{PROCESSED_BUCKET}/"
)

# ---------------------------------------------------------------------------
# 8. Compute and log aggregations
# ---------------------------------------------------------------------------

daily_rev = (
    valid_df
    .groupBy("order_date")
    .agg(F.sum("line_revenue").alias("total_revenue"))
    .orderBy("order_date")
)

payment_rate = (
    valid_df
    .groupBy("order_date")
    .agg(
        F.count("order_id").alias("total_orders"),
        F.sum(F.when(F.col("payment_status") == "paid", 1).otherwise(0)).alias("paid_orders"),
    )
    .withColumn("success_rate", F.col("paid_orders") / F.col("total_orders"))
    .orderBy("order_date")
)

logger.info("=== Daily Revenue ===")
daily_rev.show(truncate=False)

logger.info("=== Payment Success Rate ===")
payment_rate.show(truncate=False)

logger.info(
    "Processing summary — total: %d, valid: %d, invalid: %d, after_dedup: %d",
    total_records, valid_count, invalid_count, dedup_count,
)

# ---------------------------------------------------------------------------
# Commit job bookmark
# ---------------------------------------------------------------------------

job.commit()
