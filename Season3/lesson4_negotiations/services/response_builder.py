"""Budowanie zwięzłych odpowiedzi narzędzia z limitem 500 bajtów."""

from __future__ import annotations

from models import SearchResult


def build_output(result: SearchResult) -> str:
    """Buduje komunikat wyjściowy dla agenta na podstawie wyniku wyszukiwania.

    Args:
        result: Wynik analizy i wyszukiwania.

    Returns:
        Komunikat tekstowy gotowy do zwrócenia w polu `output`.
    """

    if not result.requested_items:
        message = "Nie rozpoznano przedmiotów. Podaj listę rzeczy do kupienia."
        return enforce_output_limits(message)

    unresolved_chunk = ""
    if result.unresolved_items:
        unresolved_chunk = f" Nierozpoznane: {', '.join(result.unresolved_items)}."

    if result.cities:
        city_chunk = ", ".join(result.cities)
        item_chunk = ", ".join(result.resolved_items) if result.resolved_items else ", ".join(result.requested_items)
        message = f"Przedmioty: {item_chunk}. Miasta z kompletem: {city_chunk}.{unresolved_chunk}"
        return enforce_output_limits(message)

    item_chunk = ", ".join(result.resolved_items or result.requested_items)
    message = f"Brak miasta z kompletem dla: {item_chunk}.{unresolved_chunk}"
    return enforce_output_limits(message)


def enforce_output_limits(value: str, min_bytes: int = 4, max_bytes: int = 500) -> str:
    """Dopasowuje długość odpowiedzi do wymagań bajtowych zadania.

    Args:
        value: Oryginalna odpowiedź tekstowa.
        min_bytes: Minimalna liczba bajtów UTF-8.
        max_bytes: Maksymalna liczba bajtów UTF-8.

    Returns:
        Tekst mieszczący się w zadanym zakresie bajtów.
    """

    text = value.strip() or "Brak."
    raw = text.encode("utf-8")
    if len(raw) > max_bytes:
        cut = raw[: max_bytes - 3]
        while True:
            try:
                text = cut.decode("utf-8") + "..."
                break
            except UnicodeDecodeError:
                cut = cut[:-1]
    elif len(raw) < min_bytes:
        text = text.ljust(min_bytes, ".")
    return text

