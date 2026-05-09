"""
Data transformation layer.

Responsibilities
----------------
- Remove duplicate ``order_id`` records (keep first occurrence).
- Compute ``line_revenue = quantity * unit_price``.
- Add partition columns (``year``, ``month``, ``day``) derived from
  ``order_date`` for Parquet partitioning on S3.
- Return a clean, enriched DataFrame ready for aggregation and storage.
"""

from __future__ import annotations

import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)


def remove_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Drop rows with duplicate ``order_id`` values, keeping the first
    occurrence.

    Args:
        df: Validated DataFrame.

    Returns:
        De-duplicated DataFrame.
    """
    before = len(df)
    df = df.drop_duplicates(subset=["order_id"], keep="first").reset_index(drop=True)
    removed = before - len(df)
    if removed:
        logger.info("Removed %d duplicate order_id record(s)", removed)
    return df


def compute_line_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a ``line_revenue`` column: ``quantity * unit_price``.

    Args:
        df: DataFrame with numeric ``quantity`` and ``unit_price`` columns.

    Returns:
        DataFrame with the new ``line_revenue`` column appended.
    """
    df = df.copy()
    df["line_revenue"] = df["quantity"] * df["unit_price"]
    logger.debug("Computed line_revenue for %d rows", len(df))
    return df


def add_partition_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derive ``year``, ``month``, and ``day`` integer columns from
    ``order_date`` (``YYYY-MM-DD``).

    These columns are used as Parquet partition keys, producing the
    S3 path structure ``processed/year=YYYY/month=MM/day=DD/``.

    Args:
        df: DataFrame with a valid ``order_date`` column.

    Returns:
        DataFrame with ``year``, ``month``, ``day`` columns added.
    """
    df = df.copy()
    parsed = pd.to_datetime(df["order_date"], format="%Y-%m-%d")
    df["year"] = parsed.dt.year
    df["month"] = parsed.dt.month
    df["day"] = parsed.dt.day
    return df


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """
    Run the full transformation pipeline on a validated DataFrame.

    Steps:
        1. Remove duplicate ``order_id`` rows.
        2. Compute ``line_revenue``.
        3. Add partition columns (``year``, ``month``, ``day``).

    Args:
        df: Validated, clean DataFrame from the validation stage.

    Returns:
        Transformed DataFrame ready for aggregation and Parquet output.
    """
    logger.info("Starting transformation — input rows: %d", len(df))
    df = remove_duplicates(df)
    df = compute_line_revenue(df)
    df = add_partition_columns(df)
    logger.info("Transformation complete — output rows: %d", len(df))
    return df
