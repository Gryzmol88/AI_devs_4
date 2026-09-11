import json
from pathlib import Path
from typing import Any


def extract_birth_year(row: dict[str, Any]) -> int | None:
    """
    Wyciaga rok urodzenia z kilku mozliwych pol i formatow danych wejsciowych.
    """
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


def read_suspects() -> list[dict[str, Any]]:
    """
    Wczytuje podejrzanych z lesson2/data/input/suspects.json albo fallback
    Data/output.json i normalizuje rekordy do name, surname, birthYear.
    """
    root_dir = Path(__file__).resolve().parents[4]
    primary = root_dir / "lesson2" / "data" / "input" / "suspects.json"
    fallback = root_dir / "Data" / "output.json"
    source = primary if primary.exists() else fallback

    if not source.exists():
        raise FileNotFoundError(f"Brak pliku z podejrzanymi: {primary} oraz {fallback}")

    raw = json.loads(source.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", raw.get("answer", []))

    normalized: list[dict[str, Any]] = []
    for row in items:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name", "")).strip()
        surname = str(row.get("surname", "")).strip()
        birth_year = extract_birth_year(row)
        if name and surname and birth_year is not None:
            normalized.append({"name": name, "surname": surname, "birthYear": int(birth_year)})
    return normalized

