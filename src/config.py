"""
Pipeline configuration — all tuneable constants in one place.
Sensitive values (bucket names, SNS ARN, etc.) are read from
environment variables so nothing is hardcoded.
"""

import os
from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Schema definition
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: List[str] = [
    "order_id",
    "customer_id",
    "product_id",
    "order_date",
    "quantity",
    "unit_price",
    "payment_status",
]

COLUMN_DTYPES: dict = {
    "order_id": str,
    "customer_id": str,
    "product_id": str,
    "order_date": str,   # validated as date string; parsed later
    "quantity": float,
    "unit_price": float,
    "payment_status": str,
}

VALID_PAYMENT_STATUSES = {"paid", "pending", "failed"}

DATE_FORMAT = "%Y-%m-%d"

# ---------------------------------------------------------------------------
# Storage paths (local mode — mirrors S3 folder layout)
# ---------------------------------------------------------------------------

DATA_DIR = os.environ.get("DATA_DIR", "data")

RAW_DIR = os.path.join(DATA_DIR, "raw")
STAGE_DIR = os.path.join(DATA_DIR, "stage")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
ERRORS_DIR = os.path.join(DATA_DIR, "errors")
ARCHIVE_DIR = os.path.join(DATA_DIR, "archive")
SAMPLE_DIR = os.path.join(DATA_DIR, "sample")

# ---------------------------------------------------------------------------
# AWS resource identifiers (read from env; safe defaults for local runs)
# ---------------------------------------------------------------------------

AWS_REGION = os.environ.get("AWS_REGION", "ap-southeast-1")

S3_RAW_BUCKET = os.environ.get("S3_RAW_BUCKET", "")
S3_STAGE_BUCKET = os.environ.get("S3_STAGE_BUCKET", "")
S3_PROCESSED_BUCKET = os.environ.get("S3_PROCESSED_BUCKET", "")
S3_ERROR_BUCKET = os.environ.get("S3_ERROR_BUCKET", "")
S3_ARCHIVE_BUCKET = os.environ.get("S3_ARCHIVE_BUCKET", "")

SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

# ---------------------------------------------------------------------------
# Processing thresholds
# ---------------------------------------------------------------------------

# Fraction of bad records that triggers a critical SNS alert
CRITICAL_ERROR_RATE_THRESHOLD: float = float(
    os.environ.get("CRITICAL_ERROR_RATE_THRESHOLD", "0.2")
)
