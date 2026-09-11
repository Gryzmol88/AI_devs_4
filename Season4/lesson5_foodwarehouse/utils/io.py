"""Narzędzia zapisu wyników do katalogu output."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def ensure_output_dir(path: Path) -> Path:
    """Tworzy katalog output, jeśli nie istnieje.

    Args:
        path: Ścieżka do katalogu wynikowego.

    Returns:
        Upewniona ścieżka do katalogu output.
    """

    path.mkdir(parents=True, exist_ok=True)
    return path


def create_timestamped_output_dir(base_path: Path) -> Path:
    """Tworzy podkatalog output z timestampem dla pojedynczego uruchomienia.

    Args:
        base_path: Bazowa ścieżka katalogu output.

    Returns:
        Ścieżka do nowo utworzonego katalogu run, np. output/20260409_153012.
    """

    ensure_output_dir(base_path)
    run_name = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_path = base_path / run_name
    run_path.mkdir(parents=True, exist_ok=True)
    return run_path


def write_json(path: Path, data: Any) -> None:
    """Zapisuje dane w formacie JSON do pliku.

    Args:
        path: Ścieżka docelowa pliku.
        data: Dane serializowalne do JSON.

    Returns:
        None

    Side Effects:
        Tworzy lub nadpisuje plik na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka docelowa pliku.
        content: Treść do zapisania.

    Returns:
        None

    Side Effects:
        Tworzy lub nadpisuje plik na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
