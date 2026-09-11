"""Proste logowanie komunikatów do terminala."""

from datetime import datetime


def info(message: str) -> None:
    """Wypisuje informację o postępie programu.

    Args:
        message: Krótki komunikat statusowy.

    Returns:
        None
    """

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] INFO  {message}")


def error(message: str) -> None:
    """Wypisuje komunikat błędu do terminala.

    Args:
        message: Treść błędu.

    Returns:
        None
    """

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] ERROR {message}")

