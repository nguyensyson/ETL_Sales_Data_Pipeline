"""
Tests for src/transformer.py

Covers:
- remove_duplicates
- compute_line_revenue
- add_partition_columns
- transform (full pipeline)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.transformer import (
    add_partition_columns,
    compute_line_revenue,
    remove_duplicates,
    transform,
)


@pytest.fixture
def clean_df() -> pd.DataFrame:
    """Validated DataFrame ready for transformation."""
    return pd.DataFrame(
        {
            "order_id": ["ORD001", "ORD002", "ORD003"],
            "customer_id": ["CUST001", "CUST002", "CUST001"],
            "product_id": ["PROD001", "PROD002", "PROD003"],
            "order_date": ["2024-01-15", "2024-01-15", "2024-01-16"],
            "quantity": [2.0, 1.0, 3.0],
            "unit_price": [10.0, 50.0, 5.0],
            "payment_status": ["paid", "paid", "pending"],
        }
    )


# ---------------------------------------------------------------------------
# remove_duplicates
# ---------------------------------------------------------------------------


class TestRemoveDuplicates:
    def test_no_duplicates_unchanged(self, clean_df):
        result = remove_duplicates(clean_df)
        assert len(result) == len(clean_df)

    def test_duplicate_removed(self, clean_df):
        df_with_dup = pd.concat([clean_df, clean_df.iloc[[0]]], ignore_index=True)
        result = remove_duplicates(df_with_dup)
        assert len(result) == len(clean_df)

    def test_first_occurrence_kept(self, clean_df):
        dup_row = clean_df.iloc[[0]].copy()
        dup_row["unit_price"] = 999.0  # different value on duplicate
        df_with_dup = pd.concat([clean_df, dup_row], ignore_index=True)
        result = remove_duplicates(df_with_dup)
        # Original price should be kept, not the duplicate's 999.0
        assert result.loc[result["order_id"] == "ORD001", "unit_price"].iloc[0] == 10.0

    def test_all_duplicates_removed(self):
        df = pd.DataFrame(
            {
                "order_id": ["ORD001", "ORD001", "ORD001"],
                "customer_id": ["C1", "C1", "C1"],
                "product_id": ["P1", "P1", "P1"],
                "order_date": ["2024-01-15"] * 3,
                "quantity": [1.0, 1.0, 1.0],
                "unit_price": [10.0, 10.0, 10.0],
                "payment_status": ["paid"] * 3,
            }
        )
        result = remove_duplicates(df)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# compute_line_revenue
# ---------------------------------------------------------------------------


class TestComputeLineRevenue:
    def test_line_revenue_calculated_correctly(self, clean_df):
        result = compute_line_revenue(clean_df)
        assert "line_revenue" in result.columns
        assert result.iloc[0]["line_revenue"] == pytest.approx(20.0)   # 2 * 10
        assert result.iloc[1]["line_revenue"] == pytest.approx(50.0)   # 1 * 50
        assert result.iloc[2]["line_revenue"] == pytest.approx(15.0)   # 3 * 5

    def test_original_df_not_mutated(self, clean_df):
        _ = compute_line_revenue(clean_df)
        assert "line_revenue" not in clean_df.columns

    def test_zero_quantity_gives_zero_revenue(self):
        df = pd.DataFrame(
            {"quantity": [0.0], "unit_price": [9.99],
             "order_id": ["O1"], "customer_id": ["C1"],
             "product_id": ["P1"], "order_date": ["2024-01-15"],
             "payment_status": ["paid"]}
        )
        result = compute_line_revenue(df)
        assert result.iloc[0]["line_revenue"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# add_partition_columns
# ---------------------------------------------------------------------------


class TestAddPartitionColumns:
    def test_partition_columns_added(self, clean_df):
        result = add_partition_columns(clean_df)
        assert "year" in result.columns
        assert "month" in result.columns
        assert "day" in result.columns

    def test_partition_values_correct(self, clean_df):
        result = add_partition_columns(clean_df)
        assert result.iloc[0]["year"] == 2024
        assert result.iloc[0]["month"] == 1
        assert result.iloc[0]["day"] == 15

    def test_different_dates_get_different_partitions(self, clean_df):
        result = add_partition_columns(clean_df)
        assert result.iloc[2]["day"] == 16  # 2024-01-16


# ---------------------------------------------------------------------------
# transform (full pipeline)
# ---------------------------------------------------------------------------


class TestTransform:
    def test_transform_happy_path(self, clean_df):
        result = transform(clean_df)
        assert "line_revenue" in result.columns
        assert "year" in result.columns
        assert "month" in result.columns
        assert "day" in result.columns

    def test_transform_removes_duplicates(self, clean_df):
        df_with_dup = pd.concat([clean_df, clean_df.iloc[[0]]], ignore_index=True)
        result = transform(df_with_dup)
        assert len(result) == len(clean_df)

    def test_transform_output_row_count(self, clean_df):
        result = transform(clean_df)
        assert len(result) == len(clean_df)
