"""Normalizacja nazw i deduplikacja danych do struktury filesystem."""

from __future__ import annotations

import re
import unicodedata

from .models import ExtractedKnowledge, NormalizedKnowledge


def _ascii_text(value: str) -> str:
    """Usuwa polskie znaki i normalizuje białe znaki.

    Args:
        value: Tekst wejściowy.

    Returns:
        str: Tekst ASCII z pojedynczymi spacjami.
    """

    polish_map = str.maketrans(
        {
            "ą": "a",
            "ć": "c",
            "ę": "e",
            "ł": "l",
            "ń": "n",
            "ó": "o",
            "ś": "s",
            "ż": "z",
            "ź": "z",
            "Ą": "A",
            "Ć": "C",
            "Ę": "E",
            "Ł": "L",
            "Ń": "N",
            "Ó": "O",
            "Ś": "S",
            "Ż": "Z",
            "Ź": "Z",
        }
    )
    replaced = value.translate(polish_map)
    normalized = unicodedata.normalize("NFKD", replaced)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    compact = re.sub(r"\s+", " ", ascii_only)
    return compact.strip()


def _slug_path(value: str) -> str:
    """Konwertuje tekst na bezpieczny fragment ścieżki.

    Args:
        value: Tekst wejściowy.

    Returns:
        str: Małe litery, znaki alfanumeryczne i podkreślenia.
    """

    ascii_value = _ascii_text(value).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return slug or "unknown"


def to_slug(value: str) -> str:
    """Konwertuje dowolny tekst do bezpiecznego slug-a.

    Args:
        value: Tekst wejściowy.

    Returns:
        str: Znormalizowany identyfikator ASCII.
    """

    return _slug_path(value)


def normalize_knowledge(data: ExtractedKnowledge) -> NormalizedKnowledge:
    """Normalizuje dane wyciągnięte z notatek do postaci docelowej.

    Args:
        data: Dane ekstrakcyjne zwrócone przez parser LLM.

    Returns:
        NormalizedKnowledge: Dane znormalizowane i zdeduplikowane.
    """

    city_needs: dict[str, dict[str, int]] = {}
    person_to_city: dict[str, str] = {}
    person_display_name: dict[str, str] = {}
    item_to_cities: dict[str, list[str]] = {}

    for city in data.cities:
        city_name = _slug_path(city.name)
        needs = city_needs.setdefault(city_name, {})
        for need in city.needs:
            item_name = _slug_path(need.item)
            current = needs.get(item_name, 0)
            needs[item_name] = max(current, int(need.amount))

    for person in data.people:
        person_name = _slug_path(person.full_name)
        city_name = _slug_path(person.city)
        person_to_city[person_name] = city_name
        person_display_name[person_name] = person.full_name.strip()

    for offer in data.offers:
        item_name = _slug_path(offer.item)
        city_name = _slug_path(offer.city)
        cities = item_to_cities.setdefault(item_name, [])
        if city_name not in cities:
            cities.append(city_name)

    return NormalizedKnowledge(
        city_needs=city_needs,
        person_to_city=person_to_city,
        person_display_name=person_display_name,
        item_to_cities=item_to_cities,
    )
