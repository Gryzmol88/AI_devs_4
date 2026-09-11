"""Operacje wejścia/wyjścia dla artefaktów misji pobocznej."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def log_terminal(message: str) -> None:
    """Wypisuje krótki komunikat diagnostyczny do terminala.

    Args:
        message: Treść komunikatu.
    """

    print(f"[lesson4-side] {message}")


def ensure_output_dir(base_dir: Path, output_name: str) -> Path:
    """Tworzy katalog bazowy output, jeśli nie istnieje.

    Args:
        base_dir: Katalog bazowy aplikacji.
        output_name: Nazwa katalogu output.

    Returns:
        Ścieżka do katalogu output.
    """

    output_dir = base_dir / output_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def create_session_output_dir(output_dir: Path) -> Path:
    """Tworzy katalog sesji z aktualnym znacznikiem czasu UTC.

    Args:
        output_dir: Bazowy katalog output.

    Returns:
        Ścieżka do katalogu bieżącej sesji.
    """

    session = output_dir / f"session_{timestamp_utc()}"
    session.mkdir(parents=True, exist_ok=True)
    return session


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje dane do pliku JSON.

    Args:
        path: Ścieżka pliku docelowego.
        payload: Dane serializowalne do JSON.
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst UTF-8 do pliku.

    Args:
        path: Ścieżka pliku docelowego.
        content: Treść do zapisania.
    """

    path.write_text(content, encoding="utf-8")


def timestamp_utc() -> str:
    """Zwraca znacznik czasu UTC do nazewnictwa plików i sesji.

    Returns:
        Znacznik czasu w formacie `YYYYMMDDTHHMMSSZ`.
    """

    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

