"""Modele danych używane przez API i warstwę domenową zadania negotiations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class ToolRequest(BaseModel):
    """Reprezentuje wejściowy payload narzędzia wysyłany przez agenta.

    Atrybuty:
        params: Tekst w języku naturalnym zawierający parametry zapytania.
    """

    params: str | dict[str, Any] = Field(...)


class ToolResponse(BaseModel):
    """Reprezentuje odpowiedź narzędzia zwracaną do agenta.

    Atrybuty:
        output: Krótka odpowiedź tekstowa do wykorzystania przez agenta.
    """

    output: str = Field(..., min_length=4)


@dataclass(slots=True)
class ListingRecord:
    """Reprezentuje pojedynczy rekord oferty odczytany z pliku CSV.

    Atrybuty:
        city: Nazwa miasta.
        item: Nazwa przedmiotu.
        city_norm: Znormalizowana nazwa miasta.
        item_norm: Znormalizowana nazwa przedmiotu.
        source_file: URL źródłowego pliku CSV.
        raw: Surowy rekord CSV.
    """

    city: str
    item: str
    city_norm: str
    item_norm: str
    source_file: str
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SearchResult:
    """Przechowuje wynik analizy zapytania i wyszukiwania miast.

    Atrybuty:
        raw_query: Oryginalna treść zapytania użytkownika.
        requested_items: Przedmioty wykryte w zapytaniu.
        resolved_items: Przedmioty dopasowane do bazy wiedzy.
        unresolved_items: Przedmioty nierozpoznane lub niedostępne w bazie.
        cities: Miasta mające jednocześnie wszystkie dopasowane przedmioty.
        notes: Dodatkowe informacje diagnostyczne.
    """

    raw_query: str
    requested_items: list[str]
    resolved_items: list[str]
    unresolved_items: list[str]
    cities: list[str]
    notes: list[str]
