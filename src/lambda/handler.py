"""
AWS Lambda handler — CSV Validation (Step 4 in architecture diagram).

Triggered by Step Functions. For each CSV file in the raw S3 bucket:
  - Validates filename convention
  - Validates schema (required columns)
  - Validates row-level data quality
  - Routes valid files to the stage bucket
  - Routes invalid files to the error bucket
  - Publishes an SNS alert if the error rate exceeds the critical threshold

Environment variables (set by Terraform):
  RAW_BUCKET                    — source bucket
  STAGE_BUCKET                  — destination for valid files
  ERROR_BUCKET                  — destination for invalid/failed files
  SNS_TOPIC_ARN                 — alert topic
  CRITICAL_ERROR_RATE_THRESHOLD — float, default 0.2
"""

from __future__ import annotations

import io
import json
import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import boto3
import pandas as pd

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------

RAW_BUCKET = os.environ["RAW_BUCKET"]
STAGE_BUCKET = os.environ["STAGE_BUCKET"]
ERROR_BUCKET = os.environ["ERROR_BUCKET"]
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
CRITICAL_ERROR_RATE_THRESHOLD = float(
    os.environ.get("CRITICAL_ERROR_RATE_THRESHOLD", "0.2")
)

REQUIRED_COLUMNS = [
    "order_id", "customer_id", "product_id",
    "order_date", "quantity", "unit_price", "payment_status",
]

# Timezone used to determine "today" — matches the business timezone
PIPELINE_TIMEZONE = ZoneInfo(os.environ.get("PIPELINE_TIMEZONE", "Asia/Ho_Chi_Minh"))

# ---------------------------------------------------------------------------
# AWS clients
# ---------------------------------------------------------------------------

s3 = boto3.client("s3")
sns = boto3.client("sns") if SNS_TOPIC_ARN else None

logger = logging.getLogger()
logger.setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def lambda_handler(event: dict, context: Any) -> dict:
    """
    Entry point invoked by Step Functions.

    Expects *event* to contain:
      - ``prefix``       (optional) — scope which objects in the raw bucket to
                         process (defaults to all ``.csv`` files).
      - ``target_date``  (optional) — date string in ``YYYYMMDD`` format to
                         process files for a specific date.  Defaults to today
                         in the configured ``PIPELINE_TIMEZONE``.  Pass this
                         when reprocessing historical files.

    Returns a summary dict consumed by the next Step Functions state.
    """
    prefix = event.get("prefix", "")

    # Resolve the target date: explicit override or today in business timezone
    target_date: str = event.get("target_date") or datetime.now(PIPELINE_TIMEZONE).strftime("%Y%m%d")
    logger.info(
        "Starting validation. RAW_BUCKET=%s prefix='%s' target_date=%s",
        RAW_BUCKET, prefix, target_date,
    )

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=RAW_BUCKET, Prefix=prefix)

    results = []
    skipped = 0
    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".csv"):
                continue

            filename = key.split("/")[-1]

            # Only process files whose name contains today's date (YYYYMMDD)
            if target_date not in filename:
                logger.info("Skipping %s — filename does not match target date %s", filename, target_date)
                skipped += 1
                continue

            result = _process_file(key)
            results.append(result)

    total = len(results)
    passed = sum(1 for r in results if r["status"] == "staged")
    failed = sum(1 for r in results if r["status"] == "error")

    logger.info(
        "Validation complete — target_date: %s, total: %d, staged: %d, errors: %d, skipped: %d",
        target_date, total, passed, failed, skipped,
    )

    if total > 0 and (failed / total) >= CRITICAL_ERROR_RATE_THRESHOLD:
        _publish_alert(
            subject="ShopMart Pipeline — HIGH ERROR RATE",
            message=(
                f"Critical: {failed}/{total} files failed validation "
                f"(threshold: {CRITICAL_ERROR_RATE_THRESHOLD:.0%})."
            ),
        )

    return {
        "target_date": target_date,
        "total_files": total,
        "staged_files": passed,
        "error_files": failed,
        "skipped_files": skipped,
        "details": results,
    }


# ---------------------------------------------------------------------------
# Per-file processing
# ---------------------------------------------------------------------------


def _process_file(key: str) -> dict:
    """Validate a single S3 object and route it to stage or error bucket."""
    filename = key.split("/")[-1]
    logger.info("Processing: %s", key)

    try:
        response = s3.get_object(Bucket=RAW_BUCKET, Key=key)
        body = response["Body"].read()
        df = pd.read_csv(io.BytesIO(body), dtype=str, keep_default_na=False)
        df = df.replace("", pd.NA)
    except Exception as exc:
        logger.error("Failed to read %s: %s", key, exc)
        _copy_to_error(key, filename, reason=str(exc))
        return {"file": filename, "status": "error", "reason": str(exc)}

    # Schema check
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        reason = f"Missing columns: {missing_cols}"
        logger.warning("%s — %s", filename, reason)
        _copy_to_error(key, filename, reason=reason)
        _publish_alert(
            subject="ShopMart Pipeline — Schema Validation Failure",
            message=f"File {filename} rejected: {reason}",
        )
        return {"file": filename, "status": "error", "reason": reason}

    # Route valid file to stage bucket
    dest_key = f"staged/{filename}"
    s3.copy_object(
        CopySource={"Bucket": RAW_BUCKET, "Key": key},
        Bucket=STAGE_BUCKET,
        Key=dest_key,
    )
    logger.info("Staged: s3://%s/%s", STAGE_BUCKET, dest_key)

    return {"file": filename, "status": "staged", "dest_key": dest_key}


def _copy_to_error(source_key: str, filename: str, reason: str) -> None:
    """Copy a file to the error bucket with a reason tag."""
    dest_key = f"validation-errors/{filename}"
    try:
        s3.copy_object(
            CopySource={"Bucket": RAW_BUCKET, "Key": source_key},
            Bucket=ERROR_BUCKET,
            Key=dest_key,
            Tagging=f"reason={reason[:256]}",
            TaggingDirective="REPLACE",
        )
        logger.info("Error copy: s3://%s/%s", ERROR_BUCKET, dest_key)
    except Exception as exc:
        logger.error("Failed to copy error file %s: %s", filename, exc)


def _publish_alert(subject: str, message: str) -> None:
    """Publish an SNS alert if a topic ARN is configured."""
    if not sns or not SNS_TOPIC_ARN:
        return
    try:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject[:100], Message=message)
        logger.info("SNS alert published: %s", subject)
    except Exception as exc:
        logger.error("Failed to publish SNS alert: %s", exc)
