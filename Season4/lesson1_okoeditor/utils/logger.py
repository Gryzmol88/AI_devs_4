"""Proste logowanie terminalowe dla przebiegu programu."""

from datetime import datetime


def _stamp() -> str:
    """Buduje znacznik czasu do komunikatów logów.

    Returns:
        Sformatowany znacznik czasu `HH:MM:SS`.
    """

    return datetime.now().strftime("%H:%M:%S")


def log_info(message: str) -> None:
    """Wyświetla komunikat informacyjny.

    Args:
        message: Treść komunikatu do pokazania w terminalu.
    """

    print(f"[{_stamp()}] [INFO] {message}")


def log_warn(message: str) -> None:
    """Wyświetla komunikat ostrzegawczy.

    Args:
        message: Treść komunikatu do pokazania w terminalu.
    """

    print(f"[{_stamp()}] [WARN] {message}")


def log_error(message: str) -> None:
    """Wyświetla komunikat o błędzie.

    Args:
        message: Treść komunikatu do pokazania w terminalu.
    """

    print(f"[{_stamp()}] [ERROR] {message}")

