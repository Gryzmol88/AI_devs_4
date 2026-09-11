"""Prosty logger terminalowy dla programu windpower."""

from datetime import datetime


def _stamp() -> str:
    """Tworzy znacznik czasu dla logow.

    Returns:
        Aktualny czas w formacie HH:MM:SS.
    """

    return datetime.now().strftime("%H:%M:%S")


def log_info(message: str) -> None:
    """Wyswietla komunikat informacyjny.

    Args:
        message: Tresc komunikatu.
    """

    print(f"[{_stamp()}] [INFO] {message}")


def log_warn(message: str) -> None:
    """Wyswietla komunikat ostrzegawczy.

    Args:
        message: Tresc komunikatu.
    """

    print(f"[{_stamp()}] [WARN] {message}")


def log_error(message: str) -> None:
    """Wyswietla komunikat o bledzie.

    Args:
        message: Tresc komunikatu.
    """

    print(f"[{_stamp()}] [ERROR] {message}")
