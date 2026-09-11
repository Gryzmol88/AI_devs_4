"""Proste logowanie komunikatów etapowych do terminala."""

from datetime import datetime


def log_info(message: str) -> None:
    """Wypisuje krótki komunikat informacyjny na terminal.

    Args:
        message: Treść komunikatu.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[INFO {timestamp}] {message}")


def log_error(message: str) -> None:
    """Wypisuje komunikat błędu na terminal.

    Args:
        message: Treść komunikatu.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[ERROR {timestamp}] {message}")
