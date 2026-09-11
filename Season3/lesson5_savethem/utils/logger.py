"""Narzędzia logowania terminalowego dla aplikacji `savethem`."""

from __future__ import annotations

import logging
import sys


def configure_logger(name: str, level: str) -> logging.Logger:
    """Konfiguruje logger z krótkim i czytelnym formatem.

    Args:
        name: Nazwa loggera.
        level: Poziom logowania (`INFO`, `DEBUG`, itp.).

    Returns:
        Skonfigurowana instancja loggera gotowa do użycia.
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

