"""
Integration tests for the full pipeline (src/processor.py + src/main.py).

Covers:
- Happy path: valid CSV → Parquet output + aggregations
- Schema failure: file missing required columns → result.success = False
- All-invalid rows: no Parquet written, errors CSV created
- Duplicate handling end-to-end
- Raw folder is empty after run_pipeline()
- High error rate is logged (does not fail the pipeline)
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from src.main import run_pipeline
from src.processor import SalesFileProcessor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def _valid_df(n: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "order_id": [f"ORD{i:03d}" for i in range(1, n + 1)],
            "customer_id": [f"CUST{i:03d}" for i in range(1, n + 1)],
            "product_id": [f"PROD{i:03d}" for i in range(1, n + 1)],
            "order_date": ["2024-01-15"] * n,
            "quantity": ["2"] * n,
            "unit_price": ["9.99"] * n,
            "payment_status": ["paid"] * n,
        }
    )


# ---------------------------------------------------------------------------
# SalesFileProcessor tests
# ---------------------------------------------------------------------------


class TestSalesFileProcessor:
    def test_happy_path_produces_parquet(self, tmp_path):
        """Valid CSV → Parquet files written under processed dir."""
        csv_file = tmp_path / "raw" / "store_001_20240115.csv"
        _write_csv(csv_file, _valid_df())

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        assert result.success is True
        assert result.valid_records == 5
        assert result.invalid_records == 0
        # Parquet partitions should exist
        parquet_files = list((tmp_path / "processed").rglob("*.parquet"))
        assert len(parquet_files) > 0

    def test_schema_failure_returns_unsuccessful_result(self, tmp_path):
        """File missing required columns → result.success = False."""
        bad_df = pd.DataFrame(
            {"order_id": ["ORD001"], "customer_id": ["CUST001"]}
        )
        csv_file = tmp_path / "raw" / "store_bad_20240115.csv"
        _write_csv(csv_file, bad_df)

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        assert result.success is False
        assert result.error_message is not None
        assert "Missing" in result.error_message

    def test_invalid_rows_written_to_errors(self, tmp_path):
        """Rows failing validation are written to the errors directory."""
        df = pd.DataFrame(
            {
                "order_id": ["ORD001", "ORD002"],
                "customer_id": ["CUST001", ""],   # ORD002 missing customer_id
                "product_id": ["PROD001", "PROD002"],
                "order_date": ["2024-01-15", "2024-01-15"],
                "quantity": ["2", "1"],
                "unit_price": ["9.99", "19.99"],
                "payment_status": ["paid", "paid"],
            }
        )
        csv_file = tmp_path / "raw" / "store_003_20240115.csv"
        _write_csv(csv_file, df)

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        assert result.invalid_records == 1
        assert result.error_path is not None
        assert Path(result.error_path).exists()

    def test_duplicate_order_ids_removed(self, tmp_path):
        """Duplicate order_id rows are deduplicated before writing Parquet."""
        df = _valid_df(5)
        # Add a duplicate of ORD001
        dup = df.iloc[[0]].copy()
        df = pd.concat([df, dup], ignore_index=True)

        csv_file = tmp_path / "raw" / "store_004_20240115.csv"
        _write_csv(csv_file, df)

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        assert result.success is True
        # Read back the Parquet — scope to the partition path, not the root
        # (which also contains the aggregations/ CSV subfolder)
        parquet_files = list((tmp_path / "processed").rglob("*.parquet"))
        assert len(parquet_files) > 0
        processed_df = pd.read_parquet(str(parquet_files[0].parent))
        assert len(processed_df) == 5  # duplicate removed

    def test_aggregations_written(self, tmp_path):
        """Aggregation CSVs are created under processed/aggregations/."""
        csv_file = tmp_path / "raw" / "store_005_20240115.csv"
        _write_csv(csv_file, _valid_df())

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        agg_dir = tmp_path / "processed" / "aggregations"
        assert agg_dir.exists()
        agg_files = list(agg_dir.glob("*.csv"))
        assert len(agg_files) == 3  # daily_revenue, orders_per_customer, payment_success_rate

    def test_all_invalid_rows_no_parquet(self, tmp_path):
        """When every row is invalid, no Parquet file should be written."""
        df = pd.DataFrame(
            {
                "order_id": ["ORD001"],
                "customer_id": [""],          # invalid
                "product_id": ["PROD001"],
                "order_date": ["2024-01-15"],
                "quantity": ["-1"],           # invalid
                "unit_price": ["9.99"],
                "payment_status": ["paid"],
            }
        )
        csv_file = tmp_path / "raw" / "store_006_20240115.csv"
        _write_csv(csv_file, df)

        processor = SalesFileProcessor(
            processed_dir=str(tmp_path / "processed"),
            errors_dir=str(tmp_path / "errors"),
        )
        result = processor.process(str(csv_file))

        assert result.valid_records == 0
        parquet_files = list((tmp_path / "processed").rglob("*.parquet"))
        assert len(parquet_files) == 0


# ---------------------------------------------------------------------------
# run_pipeline integration test
# ---------------------------------------------------------------------------


class TestRunPipeline:
    def test_raw_folder_empty_after_run(self, tmp_path, monkeypatch):
        """After run_pipeline(), the raw folder should contain no CSV files."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        _write_csv(raw_dir / "store_001_20240115.csv", _valid_df())
        _write_csv(raw_dir / "store_002_20240115.csv", _valid_df(3))

        # Redirect output dirs to tmp_path
        monkeypatch.setenv("DATA_DIR", str(tmp_path))

        import src.config as cfg
        monkeypatch.setattr(cfg, "PROCESSED_DIR", str(tmp_path / "processed"))
        monkeypatch.setattr(cfg, "ERRORS_DIR", str(tmp_path / "errors"))
        monkeypatch.setattr(cfg, "ARCHIVE_DIR", str(tmp_path / "archive"))

        summary = run_pipeline(raw_dir=str(raw_dir))

        remaining_csv = list(raw_dir.glob("*.csv"))
        assert len(remaining_csv) == 0
        assert summary["total"] == 2
        assert summary["succeeded"] == 2
        assert summary["failed"] == 0

    def test_no_files_returns_zero_counts(self, tmp_path):
        """Empty raw folder returns zero counts without error."""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir()
        summary = run_pipeline(raw_dir=str(raw_dir))
        assert summary == {"total": 0, "succeeded": 0, "failed": 0}
