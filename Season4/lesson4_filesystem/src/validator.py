"""Walidacja lokalna danych przed wysłaniem do API verify."""

from __future__ import annotations

from .models import NormalizedKnowledge


def validate_before_send(data: NormalizedKnowledge) -> None:
    """Waliduje minimalne warunki poprawności danych zadania.

    Args:
        data: Dane po normalizacji.

    Returns:
        None: Funkcja nie zwraca wartości.

    Raises:
        ValueError: Gdy dane są puste lub zawierają niepoprawne elementy.
    """

    if not data.city_needs:
        raise ValueError("Brak danych o miastach i ich potrzebach.")
    if not data.person_to_city:
        raise ValueError("Brak danych o osobach odpowiedzialnych za handel.")
    if not data.item_to_cities:
        raise ValueError("Brak danych o towarach oferowanych na sprzedaż.")

    for city_slug, needs in data.city_needs.items():
        if not city_slug:
            raise ValueError("Wykryto puste ID miasta.")
        for item_slug, amount in needs.items():
            if not item_slug:
                raise ValueError(f"Wykryto pusty towar dla miasta: {city_slug}")
            if amount < 0:
                raise ValueError(
                    f"Wykryto ujemną ilość towaru '{item_slug}' dla miasta '{city_slug}'."
                )

