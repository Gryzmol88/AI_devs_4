"""Logger terminalowy + opcjonalny log plikowy."""

from datetime import datetime
from pathlib import Path

_LOG_FILE: Path | None = None


def _stamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def set_log_file(path: Path) -> None:
    """Ustawia plik logu dla biezacego uruchomienia."""

    global _LOG_FILE
    _LOG_FILE = path


def _write(level: str, message: str) -> None:
    line = f"[{_stamp()}] [{level}] {message}"
    print(line)
    if _LOG_FILE is not None:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def log_info(message: str) -> None:
    _write("INFO", message)


def log_warn(message: str) -> None:
    _write("WARN", message)


def log_error(message: str) -> None:
    _write("ERROR", message)
