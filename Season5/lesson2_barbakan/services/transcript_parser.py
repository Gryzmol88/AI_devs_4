"""Parser tekstu operatora do ekstrakcji statusu dróg i intencji."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ParsedOperatorMessage:
    """Wynik parsowania wiadomości operatora.

    Atrybuty:
        road_status: Mapa statusów dróg po kluczu nazwy drogi.
        asks_why_disable: Flaga informująca, czy operator pyta o powód wyłączenia.
        confirms_disable: Flaga informująca, czy operator potwierdził wyłączenie.
    """

    road_status: dict[str, str]
    asks_why_disable: bool
    confirms_disable: bool


def parse_operator_text(text: str) -> ParsedOperatorMessage:
    """Ekstrahuje z tekstu informacje potrzebne do sterowania dialogiem.

    Args:
        text: Odpowiedź operatora po transkrypcji.

    Returns:
        ParsedOperatorMessage: Struktura z wykrytymi sygnałami dialogowymi.
    """

    normalized = text.lower()
    roads = {"RD224": "", "RD472": "", "RD820": ""}
    for road in roads:
        pattern = rf"{road.lower()}[^.?!\n]*"
        match = re.search(pattern, normalized)
        if match:
            roads[road] = match.group(0)

    asks_why_disable = any(
        phrase in normalized
        for phrase in (
            "dlaczego",
            "z jakiego powodu",
            "po co",
            "uzasadnij",
        )
    )
    confirms_disable = any(
        phrase in normalized
        for phrase in ("wyłączy", "wyłączam", "monitoring wyłączony", "odblokow")
    )

    return ParsedOperatorMessage(
        road_status=roads,
        asks_why_disable=asks_why_disable,
        confirms_disable=confirms_disable,
    )


def choose_passable_road(road_status: dict[str, str]) -> str | None:
    """Wybiera drogę przejezdną na podstawie opisów statusów.

    Args:
        road_status: Mapa nazwa-drogi -> opis statusu.

    Returns:
        str | None: Nazwa drogi przejezdnej lub `None`, gdy brak pewnego dopasowania.
    """

    positive_markers = ("przejezd", "bezpiecz", "drożn", "otwart")
    negative_markers = ("zamk", "skaż", "nieprzejezd", "zagroż")

    for road, status in road_status.items():
        if not status:
            continue
        if any(p in status for p in positive_markers) and not any(
            n in status for n in negative_markers
        ):
            return road
    return None

