"""Narzędzia I/O do logowania i zapisu artefaktów zadania reactor."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_output_dir(base_dir: Path, output_dir_name: str) -> Path:
    """Tworzy katalog wyjściowy na pliki artefaktów.

    Args:
        base_dir: Katalog bazowy aplikacji.
        output_dir_name: Nazwa katalogu na rezultaty.

    Returns:
        Ścieżka do katalogu wyjściowego.

    Efekty uboczne:
        Tworzy katalog na dysku, jeśli nie istnieje.
    """

    output_dir = base_dir / output_dir_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def create_session_output_dir(root_output_dir: Path) -> Path:
    """Tworzy katalog sesji uruchomienia wewnątrz katalogu output.

    Args:
        root_output_dir: Główny katalog output.

    Returns:
        Ścieżka do katalogu sesji.

    Efekty uboczne:
        Tworzy podkatalog sesji oraz aktualizuje plik `latest_session.txt`.
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
    """Zwraca znacznik czasu UTC w formacie ISO 8601.

    Returns:
        Tekstowy znacznik czasu zakończony `Z`.
    """

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log_terminal(message: str) -> None:
    """Wypisuje krótki komunikat postępu do terminala.

    Args:
        message: Treść komunikatu.
    """

    print(f"[reactor-agent] {message}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Zapisuje dane słownikowe jako plik JSON.

    Args:
        path: Ścieżka pliku docelowego.
        payload: Dane do zapisu.

    Efekty uboczne:
        Nadpisuje lub tworzy wskazany plik.
    """

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka pliku docelowego.
        content: Treść tekstowa.

    Efekty uboczne:
        Nadpisuje lub tworzy wskazany plik.
    """

    path.write_text(content, encoding="utf-8")
