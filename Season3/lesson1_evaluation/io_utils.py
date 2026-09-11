"""Funkcje pomocnicze do zapisu artefaktów do katalogu output."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje payload JSON z kodowaniem UTF-8 i wcięciami.

    Args:
        path: Docelowa ścieżka pliku.
        payload: Dane serializowalne do JSON.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)


def write_text(path: Path, content: str) -> None:
    """Zapisuje zwykły tekst do pliku.

    Args:
        path: Docelowa ścieżka pliku.
        content: Treść tekstowa do zapisania.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        file.write(content)
