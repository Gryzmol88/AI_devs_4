import json
from pathlib import Path
from typing import Any


def load_cache(path: Path) -> dict[str, Any]:
    """
    Wczytuje cache JSON i zwraca pusty slownik, gdy plik jest niedostepny lub uszkodzony.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    """
    Zapisuje cache JSON na dysk, aby ograniczyc liczbe zewnetrznych zapytan.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

