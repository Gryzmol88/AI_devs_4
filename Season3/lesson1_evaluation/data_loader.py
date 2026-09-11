"""Funkcje pomocnicze do wczytywania danych sensorów i archiwów."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Iterable, List
from urllib.request import urlretrieve

from models import SensorRecord


def download_zip(url: str, destination: Path) -> Path:
    """Pobiera archiwum ZIP z danymi sensorów.

    Args:
        url: Bezpośredni URL do archiwum.
        destination: Lokalna ścieżka zapisu archiwum ZIP.

    Returns:
        Ścieżkę docelową.
    """

    destination.parent.mkdir(parents=True, exist_ok=True)
    urlretrieve(url, destination)  # nosec: B310, URL controlled by configuration
    return destination


def extract_zip(zip_path: Path, destination_dir: Path) -> None:
    """Rozpakowuje archiwum ZIP do wskazanego katalogu.

    Args:
        zip_path: Ścieżka do istniejącego pliku ZIP.
        destination_dir: Katalog docelowy dla wypakowanych plików.
    """

    destination_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as archive:
        archive.extractall(destination_dir)


def list_sensor_files(directory: Path) -> List[Path]:
    """Zwraca listę plików JSON z sensorami, posortowaną po nazwie.

    Args:
        directory: Katalog z plikami JSON.

    Returns:
        Posortowaną listę ścieżek do plików JSON.
    """

    return sorted(directory.glob("*.json"), key=lambda path: path.name)


def load_sensor_record(path: Path) -> SensorRecord:
    """Wczytuje pojedynczy plik JSON sensora do modelu typowanego.

    Args:
        path: Ścieżka do pojedynczego pliku JSON.

    Returns:
        Sparsowany obiekt SensorRecord z uzupełnionym file_id.
    """

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    payload["file_id"] = path.stem
    return SensorRecord.model_validate(payload)


def load_all_records(directory: Path) -> List[SensorRecord]:
    """Wczytuje wszystkie pliki sensorów z katalogu do pamięci.

    Args:
        directory: Katalog z plikami JSON sensorów.

    Returns:
        Listę obiektów SensorRecord.
    """

    files: Iterable[Path] = list_sensor_files(directory)
    return [load_sensor_record(path) for path in files]
