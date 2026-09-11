"""Narzędzia logowania dla aplikacji misji pobocznej."""

from __future__ import annotations

import logging
import sys


def configure_logger(name: str, level: str) -> logging.Logger:
    """Tworzy i konfiguruje logger terminalowy.

    Args:
        name: Nazwa loggera.
        level: Poziom logowania.

    Returns:
        Skonfigurowana instancja loggera.
    """

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.propagate = False
    return logger

