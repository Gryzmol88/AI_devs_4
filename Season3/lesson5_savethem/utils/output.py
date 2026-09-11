"""Operacje zapisu artefaktów działania do katalogu `output`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def create_session_output_dir(base_dir: Path, output_dir_name: str) -> Path:
    """Tworzy katalog sesji i zwraca jego ścieżkę.

    Args:
        base_dir: Katalog główny aplikacji.
        output_dir_name: Nazwa folderu przechowującego wyniki.

    Returns:
        Ścieżka do katalogu bieżącej sesji.

    Efekty uboczne:
        Tworzy katalog `output/session_<timestamp>` na dysku.
    """

    root = base_dir / output_dir_name
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session_dir = root / f"session_run_{stamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje obiekt jako czytelny plik JSON UTF-8.

    Args:
        path: Ścieżka docelowa.
        payload: Dane do serializacji.

    Returns:
        `None`.

    Efekty uboczne:
        Nadpisuje plik wynikowy, jeśli już istnieje.
    """

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka docelowa.
        content: Treść do zapisania.

    Returns:
        `None`.

    Efekty uboczne:
        Tworzy lub nadpisuje plik tekstowy.
    """

    path.write_text(content, encoding="utf-8")
