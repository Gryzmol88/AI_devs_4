import json
from pathlib import Path

from ..models import Person


def _extract_birth_year(row: dict) -> int | None:
    value = row.get("birth_year", row.get("birthYear", row.get("born")))
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    if "-" in text:
        text = text.split("-", 1)[0]
    try:
        return int(text)
    except ValueError:
        return None


def load_suspects(primary_path: Path, fallback_path: Path) -> list[Person]:
    source = primary_path if primary_path.exists() else fallback_path
    if not source.exists():
        raise FileNotFoundError(
            f"Missing suspects input. Expected {primary_path} or fallback {fallback_path}."
        )

    raw = json.loads(source.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", raw.get("answer", []))

    suspects: list[Person] = []
    for row in items:
        name = (row.get("name") or "").strip()
        surname = (row.get("surname") or "").strip()
        birth_year = _extract_birth_year(row)
        if not name or not surname or birth_year is None:
            continue
        suspects.append(Person(name=name, surname=surname, birth_year=birth_year))

    if not suspects:
        raise ValueError(f"No valid suspects found in {source}")
    return suspects

