import csv
import io
from datetime import date, datetime

import requests


def load_people(url: str) -> list[dict]:
    """Pobiera plik CSV spod wskazanego URL i zwraca listę rekordów jako słowniki.

    Funkcja wykonuje żądanie HTTP GET, waliduje status odpowiedzi i parsuje treść
    CSV przy pomocy `csv.DictReader`, dzięki czemu każdy wiersz ma postać:
    {nazwa_kolumny: wartość}.
    """
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return list(csv.DictReader(io.StringIO(resp.text)))


def _get_birth_date(row: dict) -> date:
    """Wylicza pełną datę urodzenia na podstawie danych rekordu.

    Priorytet ma pole `birthDate` (format YYYY-MM-DD). Jeśli go brakuje, używa pola
    `born` i tworzy datę 1 stycznia danego roku. Gdy oba pola są niedostępne lub
    niepoprawne, zgłasza `ValueError`.
    """
    birth_raw = (row.get("birthDate") or "").strip()
    if birth_raw:
        return datetime.strptime(birth_raw, "%Y-%m-%d").date()

    born_raw = (row.get("born") or "").strip()
    if born_raw:
        return date(int(born_raw), 1, 1)

    raise ValueError("Missing birth date")


def _normalize_city(row: dict) -> str:
    """Zwraca znormalizowaną nazwę miasta z rekordu.

    Funkcja wybiera najpierw `birthPlace`, a gdy brak, używa `city`.
    Wynik jest przycinany i zamieniany na `casefold`, aby porównania tekstu były
    odporne na różnice wielkości liter.
    """
    return (row.get("birthPlace") or row.get("city") or "").strip().casefold()


def age_on_date(birth_date: date, reference_date: date) -> int:
    """Oblicza wiek osoby w pełnych latach na wskazany dzień referencyjny."""
    age = reference_date.year - birth_date.year
    if (reference_date.month, reference_date.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


def prefilter(rows: list[dict], reference_year: int = 2026) -> list[dict]:
    """Filtruje rekordy do kandydatów spełniających kryteria zadania.

    Zostawia tylko osoby:
    - płci męskiej (`gender == "M"`),
    - w wieku 20-40 lat liczonym na 31 grudnia `reference_year`,
    - urodzone w Grudziądzu.
    Rekordy z brakami lub błędnym formatem daty są pomijane.
    """
    out = []
    reference_date = date(reference_year, 12, 31)

    for row in rows:
        try:
            birth_date = _get_birth_date(row)
            age = age_on_date(birth_date, reference_date)
        except (ValueError, TypeError):
            continue

        if (
            (row.get("gender") or "").strip().upper() == "M"
            and 20 <= age <= 40
            and _normalize_city(row) == "grudziądz"
        ):
            out.append(row)

    return out

