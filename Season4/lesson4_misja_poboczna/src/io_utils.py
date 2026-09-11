"""Funkcje zapisu artefaktów uruchomienia do katalogu output."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def create_run_output_dir(base_dir: Path) -> Path:
    """Tworzy katalog output dla pojedynczego uruchomienia.

    Args:
        base_dir: Katalog bazowy output.

    Returns:
        Path: Katalog uruchomienia z timestampem.
    """

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_text(path: Path, content: str) -> None:
    """Zapisuje tekst UTF-8 do pliku.

    Args:
        path: Ścieżka docelowa pliku.
        content: Treść tekstowa.

    Returns:
        None: Funkcja zapisuje dane na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje dane JSON w czytelnym formacie.

    Args:
        path: Ścieżka docelowa pliku.
        payload: Obiekt serializowalny do JSON.

    Returns:
        None: Funkcja zapisuje dane na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

