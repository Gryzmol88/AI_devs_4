"""Proste narzędzia logowania terminalowego postępu pipeline."""

from __future__ import annotations

from datetime import datetime


def log_step(message: str) -> None:
    """Wypisuje do terminala komunikat pipeline z timestampem.

    Args:
        message: Krótki komunikat o bieżącym etapie.
    """

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
