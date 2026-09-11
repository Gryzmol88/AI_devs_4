"""Narzędzia logowania dla aplikacji negotiations."""

from __future__ import annotations

import logging
import sys


def configure_logger(name: str = "negotiations") -> logging.Logger:
    """Konfiguruje logger aplikacji z prostym formatem terminalowym.

    Args:
        name: Nazwa loggera.

    Returns:
        Skonfigurowana instancja loggera.
    """

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger

