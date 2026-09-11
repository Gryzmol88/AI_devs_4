"""Operacje zapisu artefaktów działania do katalogu `output`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def create_session_dir(base_dir: Path, output_dir_name: str) -> Path:
    """Tworzy katalog dla pojedynczego przebiegu programu.

    Args:
        base_dir: Katalog bazowy aplikacji.
        output_dir_name: Nazwa katalogu `output`.

    Returns:
        Ścieżka do utworzonego katalogu sesji.
    """

    root = base_dir / output_dir_name
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    session_dir = root / f"session_run_{stamp}"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje payload do pliku JSON.

    Args:
        path: Ścieżka docelowa.
        payload: Dane do serializacji.
    """

    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka docelowa.
        text: Treść do zapisania.
    """

    path.write_text(text, encoding="utf-8")

