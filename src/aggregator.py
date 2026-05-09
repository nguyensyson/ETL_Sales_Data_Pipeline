"""
Aggregation layer.

Computes the three business metrics required by BR-3:
    1. Daily revenue  — total ``line_revenue`` per ``order_date``.
    2. Orders per customer — count of distinct ``order_id`` per ``customer_id``.
    3. Payment success rate — fraction of orders with ``payment_status == 'paid'``.

All results are returned as DataFrames so they can be written to
separate Parquet files or logged as summaries.
"""

from __future__ import annotations

import pandas as pd

from src.logger import get_logger

logger = get_logger(__name__)


def daily_revenue(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute total revenue grouped by ``order_date``.

    Args:
        df: Transformed DataFrame containing ``order_date`` and
            ``line_revenue`` columns.

    Returns:
        DataFrame with columns ``order_date`` and ``total_revenue``,
        sorted ascending by date.
    """
    result = (
        df.groupby("order_date", as_index=False)["line_revenue"]
        .sum()
        .rename(columns={"line_revenue": "total_revenue"})
        .sort_values("order_date")
        .reset_index(drop=True)
    )
    logger.info(
        "Daily revenue computed — %d date(s), total: %.2f",
        len(result),
        result["total_revenue"].sum(),
    )
    return result


def orders_per_customer(df: pd.DataFrame) -> pd.DataFrame:
    """
    Count distinct orders per customer.

    Args:
        df: Transformed DataFrame containing ``customer_id`` and
            ``order_id`` columns.

    Returns:
        DataFrame with columns ``customer_id`` and ``order_count``,
        sorted descending by ``order_count``.
    """
    result = (
        df.groupby("customer_id", as_index=False)["order_id"]
        .nunique()
        .rename(columns={"order_id": "order_count"})
        .sort_values("order_count", ascending=False)
        .reset_index(drop=True)
    )
    logger.info(
        "Orders per customer computed — %d unique customer(s)", len(result)
    )
    return result


def payment_success_rate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute the payment success rate (fraction of ``paid`` orders)
    grouped by ``order_date``.

    Args:
        df: Transformed DataFrame containing ``order_date`` and
            ``payment_status`` columns.

    Returns:
        DataFrame with columns ``order_date``, ``total_orders``,
        ``paid_orders``, and ``success_rate`` (0.0 – 1.0).
    """
    grouped = df.groupby("order_date")
    total = grouped["order_id"].count().rename("total_orders")
    paid = (
        df[df["payment_status"] == "paid"]
        .groupby("order_date")["order_id"]
        .count()
        .rename("paid_orders")
    )
    result = (
        pd.concat([total, paid], axis=1)
        .fillna(0)
        .astype({"paid_orders": int})
        .reset_index()
    )
    result["success_rate"] = result["paid_orders"] / result["total_orders"]
    result = result.sort_values("order_date").reset_index(drop=True)

    overall = result["paid_orders"].sum() / result["total_orders"].sum()
    logger.info("Payment success rate computed — overall: %.2f%%", overall * 100)
    return result


def aggregate(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """
    Run all three aggregations and return them in a named dict.

    Args:
        df: Transformed DataFrame.

    Returns:
        Dictionary with keys ``"daily_revenue"``, ``"orders_per_customer"``,
        and ``"payment_success_rate"``, each mapping to a DataFrame.
    """
    return {
        "daily_revenue": daily_revenue(df),
        "orders_per_customer": orders_per_customer(df),
        "payment_success_rate": payment_success_rate(df),
    }
