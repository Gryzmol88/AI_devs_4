"""Narzędzia zapisu artefaktów działania programu."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def create_run_output_dir(base_dir: Path) -> Path:
    """Tworzy katalog wynikowy dla pojedynczego uruchomienia.

    Args:
        base_dir: Bazowy katalog output.

    Returns:
        Path: Ścieżka nowego katalogu z timestampem.
    """

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = base_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku UTF-8.

    Args:
        path: Ścieżka pliku docelowego.
        content: Treść do zapisania.

    Returns:
        None: Funkcja zapisuje plik na dysku.

    Efekty uboczne:
        Tworzy brakujące katalogi nadrzędne i nadpisuje istniejący plik.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje dane JSON w czytelnej postaci.

    Args:
        path: Ścieżka pliku docelowego.
        payload: Obiekt serializowalny do JSON.

    Returns:
        None: Funkcja zapisuje plik JSON na dysku.

    Efekty uboczne:
        Tworzy brakujące katalogi nadrzędne i nadpisuje istniejący plik.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

