"""Narzędzia do prostego logowania etapów działania programu."""

from datetime import datetime


def log_info(message: str) -> None:
    """Wypisuje krótki komunikat informacyjny do terminala.

    Args:
        message: Treść komunikatu do wyświetlenia.
    """

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] INFO: {message}")


def log_error(message: str) -> None:
    """Wypisuje krótki komunikat błędu do terminala.

    Args:
        message: Treść komunikatu błędu.
    """

    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] ERROR: {message}")

