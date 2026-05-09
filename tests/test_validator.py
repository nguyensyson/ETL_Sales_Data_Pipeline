"""
Tests for src/validator.py

Covers:
- validate_filename
- validate_schema (happy path + missing columns)
- validate_rows (happy path, missing fields, negative quantity,
  bad date format, invalid payment status)
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.validator import validate_filename, validate_rows, validate_schema


# ---------------------------------------------------------------------------
# validate_filename
# ---------------------------------------------------------------------------


class TestValidateFilename:
    def test_valid_filename(self):
        assert validate_filename("store_001_20240115.csv") is True

    def test_valid_filename_alphanumeric_store_id(self):
        assert validate_filename("store_STORE01_20240115.csv") is True

    def test_missing_date_part(self):
        assert validate_filename("store_001.csv") is False

    def test_wrong_extension(self):
        assert validate_filename("store_001_20240115.txt") is False

    def test_extra_prefix(self):
        assert validate_filename("data_store_001_20240115.csv") is False


# ---------------------------------------------------------------------------
# validate_schema
# ---------------------------------------------------------------------------


class TestValidateSchema:
    def test_valid_schema(self, valid_df):
        ok, msg = validate_schema(valid_df)
        assert ok is True
        assert "valid" in msg.lower()

    def test_missing_one_column(self, df_missing_columns):
        ok, msg = validate_schema(df_missing_columns)
        assert ok is False
        assert "unit_price" in msg

    def test_missing_multiple_columns(self):
        df = pd.DataFrame({"order_id": ["ORD001"], "customer_id": ["CUST001"]})
        ok, msg = validate_schema(df)
        assert ok is False
        # At least one missing column should be mentioned
        assert "Missing" in msg

    def test_extra_columns_are_allowed(self, valid_df):
        df = valid_df.copy()
        df["extra_col"] = "extra"
        ok, _ = validate_schema(df)
        assert ok is True


# ---------------------------------------------------------------------------
# validate_rows
# ---------------------------------------------------------------------------


class TestValidateRows:
    def test_all_valid_rows(self, valid_df):
        good, bad = validate_rows(valid_df)
        assert len(good) == len(valid_df)
        assert len(bad) == 0

    def test_missing_customer_id_rejected(self, df_bad_rows):
        """Row with empty customer_id should be in invalid set."""
        good, bad = validate_rows(df_bad_rows)
        assert any("customer_id" in str(e) for e in bad["validation_error"])

    def test_negative_quantity_rejected(self, df_bad_rows):
        """Row with quantity = -5 should be rejected."""
        _, bad = validate_rows(df_bad_rows)
        assert any("quantity" in str(e) for e in bad["validation_error"])

    def test_bad_date_format_rejected(self, df_bad_rows):
        """Row with date '15/01/2024' should be rejected."""
        _, bad = validate_rows(df_bad_rows)
        assert any("order_date" in str(e) for e in bad["validation_error"])

    def test_non_numeric_price_rejected(self, df_bad_rows):
        """Row with unit_price = 'abc' should be rejected."""
        _, bad = validate_rows(df_bad_rows)
        assert any("unit_price" in str(e) for e in bad["validation_error"])

    def test_invalid_payment_status_rejected(self, df_bad_rows):
        """Row with payment_status = 'unknown' should be rejected."""
        _, bad = validate_rows(df_bad_rows)
        assert any("payment_status" in str(e) for e in bad["validation_error"])

    def test_valid_rows_have_no_validation_error_column(self, valid_df):
        good, _ = validate_rows(valid_df)
        assert "validation_error" not in good.columns

    def test_invalid_rows_have_validation_error_column(self, df_bad_rows):
        _, bad = validate_rows(df_bad_rows)
        assert "validation_error" in bad.columns

    def test_payment_status_normalised_to_lowercase(self):
        df = pd.DataFrame(
            {
                "order_id": ["ORD001"],
                "customer_id": ["CUST001"],
                "product_id": ["PROD001"],
                "order_date": ["2024-01-15"],
                "quantity": ["2"],
                "unit_price": ["9.99"],
                "payment_status": ["PAID"],
            }
        )
        good, bad = validate_rows(df)
        assert len(good) == 1
        assert good.iloc[0]["payment_status"] == "paid"
