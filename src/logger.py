"""
Centralised logging setup for the ShopMart pipeline.

Usage:
    from src.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Processing started")
"""

import logging
import sys
from typing import Optional


def get_logger(name: str, level: Optional[int] = None) -> logging.Logger:
    """
    Return a logger with a consistent format.

    Args:
        name:  Usually ``__name__`` of the calling module.
        level: Override log level (defaults to INFO).

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        # Avoid adding duplicate handlers when the module is re-imported
        return logger

    log_level = level or logging.INFO
    logger.setLevel(log_level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(log_level)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger
