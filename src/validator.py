"""
CSV schema and data-quality validation.

Responsibilities
----------------
- Check that all required columns are present.
- Coerce / verify data types.
- Flag rows with missing critical fields, negative quantities,
  invalid payment statuses, or malformed dates.
- Return two DataFrames: valid records and invalid records (with a
  ``validation_error`` column explaining the rejection reason).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

import pandas as pd

from src.config import (
    COLUMN_DTYPES,
    DATE_FORMAT,
    REQUIRED_COLUMNS,
    VALID_PAYMENT_STATUSES,
)
from src.logger import get_logger

logger = get_logger(__name__)

# Regex for the expected filename convention: store_{store_id}_{YYYYMMDD}.csv
FILENAME_PATTERN = re.compile(r"^store_\w+_\d{8}\.csv$")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_filename(filename: str) -> bool:
    """
    Check that the file name follows the convention
    ``store_{store_id}_{YYYYMMDD}.csv``.

    Args:
        filename: Bare filename (no directory path).

    Returns:
        ``True`` if the name is valid, ``False`` otherwise.
    """
    return bool(FILENAME_PATTERN.match(filename))


def validate_schema(df: pd.DataFrame) -> Tuple[bool, str]:
    """
    Verify that *df* contains all required columns.

    Args:
        df: Raw DataFrame loaded from a CSV file.

    Returns:
        A ``(is_valid, message)`` tuple.  *is_valid* is ``False`` when
        one or more required columns are missing.
    """
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        msg = f"Missing required columns: {missing}"
        logger.warning(msg)
        return False, msg
    return True, "Schema valid"


def validate_rows(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Split *df* into valid and invalid rows.

    Validation rules applied per row:

    * ``order_id``, ``customer_id``, ``product_id`` must not be null/empty.
    * ``quantity`` must be a positive number (> 0).
    * ``unit_price`` must be a non-negative number (>= 0).
    * ``order_date`` must be parseable as ``YYYY-MM-DD``.
    * ``payment_status`` must be one of ``paid``, ``pending``, ``failed``.

    Args:
        df: DataFrame that has already passed :func:`validate_schema`.

    Returns:
        ``(valid_df, invalid_df)`` — invalid rows carry an extra
        ``validation_error`` column.
    """
    df = df.copy()
    errors: list[str] = [""] * len(df)

    # --- Numeric coercion ------------------------------------------------
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")

    # --- String trimming -------------------------------------------------
    for col in ["order_id", "customer_id", "product_id", "payment_status"]:
        df[col] = df[col].astype(str).str.strip()

    # --- Row-level checks ------------------------------------------------
    for idx in df.index:
        row_errors: list[str] = []

        # Critical string fields must not be empty
        for col in ["order_id", "customer_id", "product_id"]:
            val = df.at[idx, col]
            if pd.isna(val) or str(val).strip() in ("", "nan"):
                row_errors.append(f"{col} is missing")

        # Quantity
        qty = df.at[idx, "quantity"]
        if pd.isna(qty):
            row_errors.append("quantity is missing or non-numeric")
        elif qty <= 0:
            row_errors.append(f"quantity must be > 0 (got {qty})")

        # Unit price
        price = df.at[idx, "unit_price"]
        if pd.isna(price):
            row_errors.append("unit_price is missing or non-numeric")
        elif price < 0:
            row_errors.append(f"unit_price must be >= 0 (got {price})")

        # Order date
        date_val = str(df.at[idx, "order_date"]).strip()
        if not _is_valid_date(date_val):
            row_errors.append(
                f"order_date '{date_val}' is not in YYYY-MM-DD format"
            )

        # Payment status
        status = str(df.at[idx, "payment_status"]).strip().lower()
        if status not in VALID_PAYMENT_STATUSES:
            row_errors.append(
                f"payment_status '{status}' is not in {VALID_PAYMENT_STATUSES}"
            )
        else:
            # Normalise to lowercase
            df.at[idx, "payment_status"] = status

        errors[idx] = "; ".join(row_errors)

    df["validation_error"] = errors

    invalid_mask = df["validation_error"] != ""
    valid_df = df[~invalid_mask].drop(columns=["validation_error"]).reset_index(drop=True)
    invalid_df = df[invalid_mask].reset_index(drop=True)

    logger.info(
        "Row validation complete — valid: %d, invalid: %d",
        len(valid_df),
        len(invalid_df),
    )
    return valid_df, invalid_df


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_date(value: str) -> bool:
    """Return ``True`` if *value* can be parsed as ``YYYY-MM-DD``."""
    try:
        datetime.strptime(value, DATE_FORMAT)
        return True
    except (ValueError, TypeError):
        return False
