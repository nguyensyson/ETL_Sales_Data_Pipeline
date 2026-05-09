"""
Shared pytest fixtures for the ShopMart pipeline test suite.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# DataFrame fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def valid_df() -> pd.DataFrame:
    """A fully valid sales DataFrame (10 rows, no issues)."""
    return pd.DataFrame(
        {
            "order_id": [f"ORD{i:03d}" for i in range(1, 11)],
            "customer_id": [f"CUST{i:03d}" for i in range(1, 11)],
            "product_id": [f"PROD{i:03d}" for i in range(1, 11)],
            "order_date": ["2024-01-15"] * 10,
            "quantity": [str(i) for i in range(1, 11)],
            "unit_price": ["9.99"] * 10,
            "payment_status": ["paid"] * 5 + ["pending"] * 3 + ["failed"] * 2,
        }
    )


@pytest.fixture
def df_with_duplicates(valid_df: pd.DataFrame) -> pd.DataFrame:
    """DataFrame that contains a duplicate order_id row."""
    dup = valid_df.iloc[[0]].copy()
    return pd.concat([valid_df, dup], ignore_index=True)


@pytest.fixture
def df_missing_columns() -> pd.DataFrame:
    """DataFrame missing the required 'unit_price' column."""
    return pd.DataFrame(
        {
            "order_id": ["ORD001"],
            "customer_id": ["CUST001"],
            "product_id": ["PROD001"],
            "order_date": ["2024-01-15"],
            "quantity": ["2"],
            # unit_price intentionally absent
            "payment_status": ["paid"],
        }
    )


@pytest.fixture
def df_bad_rows() -> pd.DataFrame:
    """DataFrame with several rows that should fail row-level validation."""
    return pd.DataFrame(
        {
            "order_id": ["ORD001", "ORD002", "ORD003", "ORD004", "ORD005"],
            "customer_id": ["CUST001", "", "CUST003", "CUST004", "CUST005"],
            "product_id": ["PROD001", "PROD002", "PROD003", "PROD004", "PROD005"],
            "order_date": [
                "2024-01-15",
                "2024-01-15",
                "15/01/2024",   # wrong format
                "2024-01-15",
                "2024-01-15",
            ],
            "quantity": ["2", "1", "3", "-5", "2"],   # ORD004 negative
            "unit_price": ["9.99", "19.99", "29.99", "9.99", "abc"],  # ORD005 non-numeric
            "payment_status": ["paid", "paid", "paid", "paid", "unknown"],
        }
    )


# ---------------------------------------------------------------------------
# Temporary CSV file fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_csv_path(tmp_path: Path, valid_df: pd.DataFrame) -> str:
    """Write *valid_df* to a temp CSV and return its path."""
    csv_file = tmp_path / "store_001_20240115.csv"
    valid_df.to_csv(csv_file, index=False)
    return str(csv_file)


@pytest.fixture
def bad_rows_csv_path(tmp_path: Path, df_bad_rows: pd.DataFrame) -> str:
    """Write *df_bad_rows* to a temp CSV and return its path."""
    csv_file = tmp_path / "store_002_20240115.csv"
    df_bad_rows.to_csv(csv_file, index=False)
    return str(csv_file)
