"""Narzędzia I/O do logowania i zapisu artefaktów misji pobocznej."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_output_dir(base_dir: Path, output_dir_name: str) -> Path:
    """Tworzy katalog wyjściowy, jeśli nie istnieje.

    Args:
        base_dir: Katalog bazowy aplikacji.
        output_dir_name: Nazwa katalogu wynikowego.

    Returns:
        Ścieżka do katalogu wyjściowego.

    Efekty uboczne:
        Tworzy katalog na dysku.
    """

    output_dir = base_dir / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def create_session_output_dir(root_output_dir: Path) -> Path:
    """Tworzy katalog sesji uruchomienia.

    Args:
        root_output_dir: Główny katalog output.

    Returns:
        Ścieżka do nowego katalogu sesji.

    Efekty uboczne:
        Tworzy katalog sesji i aktualizuje `latest_session.txt`.
    """

    session_id = (
        datetime.now(timezone.utc).strftime("session_%Y%m%dT%H%M%SZ")
        + "_"
        + uuid.uuid4().hex[:8]
    )
    session_dir = root_output_dir / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    (root_output_dir / "latest_session.txt").write_text(session_id, encoding="utf-8")
    return session_dir


def timestamp_utc() -> str:
    """Zwraca bieżący znacznik czasu UTC.

    Returns:
        Czas w formacie ISO 8601 zakończony `Z`.
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_terminal(message: str) -> None:
    """Wypisuje komunikat etapowy do terminala.

    Args:
        message: Treść komunikatu.
    """

    print(f"[lesson3-side] {message}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Zapisuje słownik do pliku JSON.

    Args:
        path: Ścieżka pliku docelowego.
        payload: Dane do zapisu.

    Efekty uboczne:
        Tworzy lub nadpisuje plik JSON.
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka pliku docelowego.
        content: Treść tekstowa.

    Efekty uboczne:
        Tworzy lub nadpisuje plik tekstowy.
    """

    path.write_text(content, encoding="utf-8")
