"""Operacje wejścia/wyjścia: katalog runa i zapis artefaktów."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def create_run_output_dir(base_output_dir: str, timestamp_format: str) -> Path:
    """Tworzy nowy katalog wynikowy dla pojedynczego uruchomienia.

    Args:
        base_output_dir: Ścieżka bazowa folderu output.
        timestamp_format: Format timestampu użyty w nazwie katalogu.

    Returns:
        Ścieżkę do utworzonego katalogu runa.
    """
    base_path = Path(base_output_dir)
    base_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime(timestamp_format)
    run_path = base_path / f"run_{timestamp}"
    suffix = 1
    while run_path.exists():
        run_path = base_path / f"run_{timestamp}_{suffix}"
        suffix += 1

    run_path.mkdir(parents=True, exist_ok=False)
    return run_path


def save_json(path: Path, payload: Any) -> None:
    """Zapisuje dane JSON do wskazanej ścieżki.

    Args:
        path: Docelowa ścieżka pliku.
        payload: Dane serializowalne do JSON.

    Efekty uboczne:
        Tworzy lub nadpisuje plik JSON.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, ensure_ascii=False, indent=2)


def save_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Docelowa ścieżka pliku.
        content: Treść tekstowa do zapisania.

    Efekty uboczne:
        Tworzy lub nadpisuje plik tekstowy.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file_handle:
        file_handle.write(content)
