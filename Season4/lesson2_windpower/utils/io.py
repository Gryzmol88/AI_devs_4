"""Operacje wejscia/wyjscia dla artefaktow uruchomienia."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> None:
    """Tworzy katalog, jesli nie istnieje.

    Args:
        path: Sciezka katalogu.

    Side Effects:
        Moze utworzyc katalog i katalogi nadrzedne.
    """

    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje dane JSON do pliku.

    Args:
        path: Sciezka pliku wynikowego.
        payload: Dane serializowalne do JSON.

    Side Effects:
        Zapisuje plik JSON na dysku.
    """

    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    """Zapisuje tekst do pliku.

    Args:
        path: Sciezka pliku wynikowego.
        text: Tresc do zapisania.

    Side Effects:
        Zapisuje plik tekstowy na dysku.
    """

    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")
