"""
Tests for src/aggregator.py

Covers:
- daily_revenue correctness
- orders_per_customer correctness
- payment_success_rate correctness
- aggregate() returns all three keys
- Edge cases: single date, all-failed payments, single customer
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.aggregator import (
    aggregate,
    daily_revenue,
    orders_per_customer,
    payment_success_rate,
)


@pytest.fixture
def transformed_df() -> pd.DataFrame:
    """Transformed DataFrame (post-transformer) used across aggregation tests."""
    return pd.DataFrame(
        {
            "order_id": ["ORD001", "ORD002", "ORD003", "ORD004", "ORD005"],
            "customer_id": ["CUST001", "CUST002", "CUST001", "CUST003", "CUST002"],
            "product_id": ["P1", "P2", "P3", "P1", "P2"],
            "order_date": [
                "2024-01-15",
                "2024-01-15",
                "2024-01-15",
                "2024-01-16",
                "2024-01-16",
            ],
            "quantity": [2.0, 1.0, 3.0, 1.0, 2.0],
            "unit_price": [10.0, 50.0, 5.0, 20.0, 30.0],
            "line_revenue": [20.0, 50.0, 15.0, 20.0, 60.0],
            "payment_status": ["paid", "paid", "pending", "failed", "paid"],
            "year": [2024, 2024, 2024, 2024, 2024],
            "month": [1, 1, 1, 1, 1],
            "day": [15, 15, 15, 16, 16],
        }
    )


# ---------------------------------------------------------------------------
# daily_revenue
# ---------------------------------------------------------------------------


class TestDailyRevenue:
    def test_correct_totals(self, transformed_df):
        result = daily_revenue(transformed_df)
        assert len(result) == 2
        jan15 = result.loc[result["order_date"] == "2024-01-15", "total_revenue"].iloc[0]
        jan16 = result.loc[result["order_date"] == "2024-01-16", "total_revenue"].iloc[0]
        assert jan15 == pytest.approx(85.0)   # 20 + 50 + 15
        assert jan16 == pytest.approx(80.0)   # 20 + 60

    def test_sorted_ascending_by_date(self, transformed_df):
        result = daily_revenue(transformed_df)
        dates = result["order_date"].tolist()
        assert dates == sorted(dates)

    def test_single_date(self):
        df = pd.DataFrame(
            {"order_date": ["2024-01-15", "2024-01-15"],
             "line_revenue": [100.0, 200.0]}
        )
        result = daily_revenue(df)
        assert len(result) == 1
        assert result.iloc[0]["total_revenue"] == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# orders_per_customer
# ---------------------------------------------------------------------------


class TestOrdersPerCustomer:
    def test_correct_counts(self, transformed_df):
        result = orders_per_customer(transformed_df)
        cust1 = result.loc[result["customer_id"] == "CUST001", "order_count"].iloc[0]
        cust2 = result.loc[result["customer_id"] == "CUST002", "order_count"].iloc[0]
        cust3 = result.loc[result["customer_id"] == "CUST003", "order_count"].iloc[0]
        assert cust1 == 2
        assert cust2 == 2
        assert cust3 == 1

    def test_sorted_descending(self, transformed_df):
        result = orders_per_customer(transformed_df)
        counts = result["order_count"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_single_customer(self):
        df = pd.DataFrame(
            {"customer_id": ["CUST001", "CUST001"],
             "order_id": ["ORD001", "ORD002"]}
        )
        result = orders_per_customer(df)
        assert len(result) == 1
        assert result.iloc[0]["order_count"] == 2


# ---------------------------------------------------------------------------
# payment_success_rate
# ---------------------------------------------------------------------------


class TestPaymentSuccessRate:
    def test_correct_rates(self, transformed_df):
        result = payment_success_rate(transformed_df)
        jan15 = result.loc[result["order_date"] == "2024-01-15"]
        jan16 = result.loc[result["order_date"] == "2024-01-16"]
        # Jan 15: 2 paid out of 3 → 0.6667
        assert jan15.iloc[0]["success_rate"] == pytest.approx(2 / 3, rel=1e-3)
        # Jan 16: 1 paid out of 2 → 0.5
        assert jan16.iloc[0]["success_rate"] == pytest.approx(0.5)

    def test_all_paid(self):
        df = pd.DataFrame(
            {"order_date": ["2024-01-15"] * 3,
             "order_id": ["O1", "O2", "O3"],
             "payment_status": ["paid", "paid", "paid"]}
        )
        result = payment_success_rate(df)
        assert result.iloc[0]["success_rate"] == pytest.approx(1.0)

    def test_all_failed(self):
        df = pd.DataFrame(
            {"order_date": ["2024-01-15"] * 3,
             "order_id": ["O1", "O2", "O3"],
             "payment_status": ["failed", "failed", "failed"]}
        )
        result = payment_success_rate(df)
        assert result.iloc[0]["success_rate"] == pytest.approx(0.0)

    def test_columns_present(self, transformed_df):
        result = payment_success_rate(transformed_df)
        for col in ["order_date", "total_orders", "paid_orders", "success_rate"]:
            assert col in result.columns


# ---------------------------------------------------------------------------
# aggregate
# ---------------------------------------------------------------------------


class TestAggregate:
    def test_returns_all_keys(self, transformed_df):
        result = aggregate(transformed_df)
        assert "daily_revenue" in result
        assert "orders_per_customer" in result
        assert "payment_success_rate" in result

    def test_all_values_are_dataframes(self, transformed_df):
        result = aggregate(transformed_df)
        for key, val in result.items():
            assert isinstance(val, pd.DataFrame), f"{key} is not a DataFrame"
