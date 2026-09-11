"""Silnik wyszukiwania miast z kompletem wymaganych przedmiotów."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from models import ListingRecord, SearchResult
from services.query_parser import QueryParser
from services.text_utils import normalize_text, unique_preserve_order


@dataclass(slots=True)
class NegotiationsSearchEngine:
    """Przechowuje indeks ofert i wykonuje zapytania o miasta.

    Atrybuty:
        records: Lista rekordów ofert z CSV.
    """

    records: list[ListingRecord]
    known_items: list[str] = field(init=False)
    item_norm_to_display: dict[str, str] = field(init=False)
    item_norm_to_cities: dict[str, set[str]] = field(init=False)

    def __post_init__(self) -> None:
        """Buduje pomocnicze indeksy po inicjalizacji obiektu."""

        self.known_items: list[str] = self._build_known_items()
        self.item_norm_to_display = {normalize_text(item): item for item in self.known_items}
        self.item_norm_to_cities: dict[str, set[str]] = {}
        for record in self.records:
            self.item_norm_to_cities.setdefault(record.item_norm, set()).add(record.city)

    def search(self, query: str, parser: QueryParser) -> SearchResult:
        """Wyszukuje miasta mające jednocześnie wszystkie przedmioty z zapytania.

        Args:
            query: Surowe zapytanie wejściowe.
            parser: Parser odpowiedzialny za ekstrakcję przedmiotów.

        Returns:
            Obiekt `SearchResult` z listą dopasowanych miast i diagnostyką.
        """

        requested_items = parser.extract_items(query=query, known_items=self.known_items)
        if not requested_items:
            return SearchResult(
                raw_query=query,
                requested_items=[],
                resolved_items=[],
                unresolved_items=[],
                cities=[],
                notes=["Brak rozpoznanych przedmiotów w zapytaniu."],
            )

        resolved_items: list[str] = []
        unresolved_items: list[str] = []
        city_sets: list[set[str]] = []
        for requested in requested_items:
            matched = self._resolve_to_known_item(requested)
            if not matched:
                unresolved_items.append(requested)
                continue
            resolved_items.append(matched)
            city_sets.append(self.item_norm_to_cities.get(normalize_text(matched), set()))

        if not city_sets:
            return SearchResult(
                raw_query=query,
                requested_items=requested_items,
                resolved_items=unique_preserve_order(resolved_items),
                unresolved_items=unique_preserve_order(unresolved_items),
                cities=[],
                notes=["Nie znaleziono dopasowań przedmiotów do danych CSV."],
            )

        common_cities = set(city_sets[0])
        for city_group in city_sets[1:]:
            common_cities &= city_group

        return SearchResult(
            raw_query=query,
            requested_items=requested_items,
            resolved_items=unique_preserve_order(resolved_items),
            unresolved_items=unique_preserve_order(unresolved_items),
            cities=sorted(common_cities),
            notes=[],
        )

    def _build_known_items(self) -> list[str]:
        """Buduje listę unikalnych nazw przedmiotów ze wszystkich rekordów.

        Returns:
            Lista unikalnych nazw przedmiotów.
        """

        seen: set[str] = set()
        result: list[str] = []
        for record in self.records:
            key = record.item_norm
            if key in seen:
                continue
            seen.add(key)
            result.append(record.item)
        return sorted(result, key=lambda value: normalize_text(value))

    def _resolve_to_known_item(self, item_name: str) -> str | None:
        """Dopasowuje nazwę przedmiotu do najbliższej pozycji ze słownika.

        Args:
            item_name: Nazwa przedmiotu do dopasowania.

        Returns:
            Kanoniczna nazwa przedmiotu lub `None` przy braku dopasowania.
        """

        normalized = normalize_text(item_name)
        if normalized in self.item_norm_to_display:
            return self.item_norm_to_display[normalized]

        matches = difflib.get_close_matches(normalized, list(self.item_norm_to_display), n=1, cutoff=0.84)
        if matches:
            return self.item_norm_to_display[matches[0]]
        return None
