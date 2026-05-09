"""
Pipeline entry point.

Scans the raw data directory for CSV files, processes each one through
the full ETL pipeline, then moves files to archive (success) or error
(failure) folders — leaving the raw folder empty after each run.

Usage:
    python src/main.py
    DATA_DIR=data python src/main.py
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from src.config import (
    ARCHIVE_DIR,
    CRITICAL_ERROR_RATE_THRESHOLD,
    ERRORS_DIR,
    PROCESSED_DIR,
    RAW_DIR,
)
from src.logger import get_logger
from src.processor import SalesFileProcessor

logger = get_logger(__name__)


def _ensure_dirs() -> None:
    """Create all required local directories if they do not exist."""
    for d in [RAW_DIR, PROCESSED_DIR, ERRORS_DIR, ARCHIVE_DIR]:
        Path(d).mkdir(parents=True, exist_ok=True)


def _move_file(src: Path, dest_dir: Path) -> None:
    """Move *src* into *dest_dir*, creating the directory if needed."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.move(str(src), str(dest))
    logger.info("Moved %s → %s", src.name, dest_dir)


def run_pipeline(raw_dir: str = RAW_DIR) -> dict:
    """
    Process all CSV files found in *raw_dir*.

    After processing each file:
    - Successful files are moved to the archive folder.
    - Failed files are moved to the errors folder.

    Args:
        raw_dir: Path to the folder containing raw CSV uploads.

    Returns:
        Summary dict with counts of processed, succeeded, and failed files.
    """
    _ensure_dirs()

    raw_path = Path(raw_dir)
    csv_files = sorted(raw_path.glob("*.csv"))

    if not csv_files:
        logger.warning("No CSV files found in %s — nothing to process.", raw_dir)
        return {"total": 0, "succeeded": 0, "failed": 0}

    logger.info("Found %d CSV file(s) to process.", len(csv_files))

    processor = SalesFileProcessor(
        processed_dir=PROCESSED_DIR,
        errors_dir=ERRORS_DIR,
    )

    succeeded = 0
    failed = 0

    for csv_file in csv_files:
        logger.info("--- Processing: %s ---", csv_file.name)
        result = processor.process(str(csv_file))

        if result.success:
            # Check if error rate exceeds critical threshold
            if result.total_records > 0:
                error_rate = result.invalid_records / result.total_records
                if error_rate >= CRITICAL_ERROR_RATE_THRESHOLD:
                    logger.warning(
                        "High error rate %.1f%% in %s (threshold: %.1f%%)",
                        error_rate * 100,
                        csv_file.name,
                        CRITICAL_ERROR_RATE_THRESHOLD * 100,
                    )
            _move_file(csv_file, Path(ARCHIVE_DIR))
            succeeded += 1
        else:
            _move_file(csv_file, Path(ERRORS_DIR))
            failed += 1

    summary = {
        "total": len(csv_files),
        "succeeded": succeeded,
        "failed": failed,
    }

    logger.info(
        "Pipeline complete — total: %d, succeeded: %d, failed: %d",
        summary["total"],
        summary["succeeded"],
        summary["failed"],
    )
    return summary


if __name__ == "__main__":
    summary = run_pipeline()
    sys.exit(0 if summary["failed"] == 0 else 1)
