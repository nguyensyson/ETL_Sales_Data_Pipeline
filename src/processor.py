"""
Core pipeline processor.

Orchestrates the full ETL flow for a single CSV file:
    1. Load CSV from the raw/stage folder.
    2. Validate schema (file-level) → reject entire file if schema is broken.
    3. Validate rows → split into valid / invalid.
    4. Transform valid rows (dedup, line_revenue, partition columns).
    5. Aggregate metrics.
    6. Persist:
       - Transformed records  → ``processed/year=YYYY/month=MM/day=DD/``
       - Invalid records      → ``errors/``
       - Aggregation CSVs     → ``processed/aggregations/``
    7. Return a :class:`ProcessingResult` summary.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

from src import aggregator, transformer, validator
from src.config import ERRORS_DIR, PROCESSED_DIR
from src.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ProcessingResult:
    """Summary of a single file's processing run."""

    filename: str
    total_records: int = 0
    valid_records: int = 0
    invalid_records: int = 0
    duplicate_count: int = 0
    processing_duration_seconds: float = 0.0
    output_path: Optional[str] = None
    error_path: Optional[str] = None
    aggregations: Dict[str, pd.DataFrame] = field(default_factory=dict)
    success: bool = True
    error_message: Optional[str] = None

    def log_summary(self) -> None:
        """Emit a structured summary to the logger."""
        logger.info("=" * 60)
        logger.info("Processing summary — %s", self.filename)
        logger.info("  Total records      : %d", self.total_records)
        logger.info("  Valid records      : %d", self.valid_records)
        logger.info("  Invalid records    : %d", self.invalid_records)
        logger.info("  Duplicates removed : %d", self.duplicate_count)
        logger.info("  Duration           : %.2fs", self.processing_duration_seconds)
        logger.info("  Output path        : %s", self.output_path or "—")
        logger.info("  Error path         : %s", self.error_path or "—")
        if not self.success:
            logger.error("  FAILED             : %s", self.error_message)
        logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------


class SalesFileProcessor:
    """
    Processes a single sales CSV file through the full ETL pipeline.

    Args:
        processed_dir: Root directory for Parquet output.
        errors_dir:    Directory for rejected records.
    """

    def __init__(
        self,
        processed_dir: str = PROCESSED_DIR,
        errors_dir: str = ERRORS_DIR,
    ) -> None:
        self.processed_dir = Path(processed_dir)
        self.errors_dir = Path(errors_dir)
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        self.errors_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def process(self, file_path: str) -> ProcessingResult:
        """
        Run the full ETL pipeline for *file_path*.

        Args:
            file_path: Absolute or relative path to the CSV file.

        Returns:
            :class:`ProcessingResult` with all metrics populated.
        """
        filename = Path(file_path).name
        result = ProcessingResult(filename=filename)
        start = time.time()

        try:
            # 1. Load
            df_raw = self._load_csv(file_path)
            result.total_records = len(df_raw)

            # 2. Schema validation
            schema_ok, schema_msg = validator.validate_schema(df_raw)
            if not schema_ok:
                result.success = False
                result.error_message = schema_msg
                result.processing_duration_seconds = time.time() - start
                result.log_summary()
                return result

            # 3. Row-level validation
            valid_df, invalid_df = validator.validate_rows(df_raw)
            result.valid_records = len(valid_df)
            result.invalid_records = len(invalid_df)

            # Persist invalid records
            if not invalid_df.empty:
                result.error_path = self._write_errors(invalid_df, filename)

            if valid_df.empty:
                logger.warning("No valid records in %s — skipping transform.", filename)
                result.processing_duration_seconds = time.time() - start
                result.log_summary()
                return result

            # 4. Transform
            before_dedup = len(valid_df)
            transformed_df = transformer.transform(valid_df)
            result.duplicate_count = before_dedup - len(
                transformed_df.drop_duplicates(subset=["order_id"])
            )

            # 5. Aggregate
            result.aggregations = aggregator.aggregate(transformed_df)
            self._write_aggregations(result.aggregations, filename)

            # 6. Persist processed Parquet (partitioned by year/month/day)
            result.output_path = self._write_parquet(transformed_df, filename)

        except Exception as exc:  # pylint: disable=broad-except
            logger.exception("Unexpected error processing %s", filename)
            result.success = False
            result.error_message = str(exc)

        finally:
            result.processing_duration_seconds = time.time() - start
            result.log_summary()

        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_csv(self, file_path: str) -> pd.DataFrame:
        """Load a CSV file into a DataFrame with all columns as strings initially."""
        logger.info("Loading file: %s", file_path)
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        # Replace empty strings with NaN for consistent null handling
        df = df.replace("", pd.NA)
        logger.info("Loaded %d rows from %s", len(df), file_path)
        return df

    def _write_parquet(self, df: pd.DataFrame, source_filename: str) -> str:
        """
        Write *df* to Parquet, partitioned by ``year/month/day``.

        Returns the root output directory path.
        """
        output_root = str(self.processed_dir)
        df.to_parquet(
            output_root,
            engine="pyarrow",
            partition_cols=["year", "month", "day"],
            index=False,
            existing_data_behavior="overwrite_or_ignore",
        )
        logger.info(
            "Parquet written to %s (partitioned by year/month/day)", output_root
        )
        return output_root

    def _write_errors(self, invalid_df: pd.DataFrame, source_filename: str) -> str:
        """Write invalid records to a CSV in the errors directory."""
        stem = Path(source_filename).stem
        error_file = self.errors_dir / f"{stem}_errors.csv"
        invalid_df.to_csv(error_file, index=False)
        logger.info("Invalid records written to %s", error_file)
        return str(error_file)

    def _write_aggregations(
        self, aggregations: Dict[str, pd.DataFrame], source_filename: str
    ) -> None:
        """Write each aggregation DataFrame to a CSV under processed/aggregations/."""
        agg_dir = self.processed_dir / "aggregations"
        agg_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(source_filename).stem
        for name, agg_df in aggregations.items():
            out_path = agg_dir / f"{stem}_{name}.csv"
            agg_df.to_csv(out_path, index=False)
            logger.info("Aggregation '%s' written to %s", name, out_path)
