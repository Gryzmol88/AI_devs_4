"""Funkcje zapisu artefaktów do katalogu `output`."""

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    """Tworzy katalog, jeśli jeszcze nie istnieje.

    Args:
        path: Ścieżka katalogu do utworzenia.

    Side Effects:
        Tworzy brakujące katalogi na dysku.
    """

    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    """Zapisuje dane do pliku JSON.

    Args:
        path: Ścieżka docelowego pliku.
        data: Dane do serializacji.

    Side Effects:
        Tworzy lub nadpisuje plik na dysku.
    """

    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_text(path: Path, text: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Ścieżka docelowego pliku.
        text: Treść tekstowa do zapisu.

    Side Effects:
        Tworzy lub nadpisuje plik na dysku.
    """

    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")

