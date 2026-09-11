"""Przetwarzanie transkrypcji rozmow radiowych."""

from __future__ import annotations

import re
from typing import Any


_POLISH_NUMBER_WORDS: dict[str, int] = {
    "zero": 0,
    "jeden": 1,
    "jedna": 1,
    "jedno": 1,
    "dwa": 2,
    "dwie": 2,
    "trzy": 3,
    "cztery": 4,
    "piec": 5,
    "pięć": 5,
    "szesc": 6,
    "sześć": 6,
    "siedem": 7,
    "osiem": 8,
    "dziewiec": 9,
    "dziewięć": 9,
    "dziesiec": 10,
    "dziesięć": 10,
    "jedenascie": 11,
    "jedenaście": 11,
    "dwanascie": 12,
    "dwanaście": 12,
}

_POLISH_ORDINAL_WORDS: dict[str, int] = {
    "pierwszego": 1,
    "drugiego": 2,
    "trzeciego": 3,
    "czwartego": 4,
    "piatego": 5,
    "piątego": 5,
    "szostego": 6,
    "szóstego": 6,
    "siodmego": 7,
    "siódmego": 7,
    "osmego": 8,
    "ósmego": 8,
    "dziewiatego": 9,
    "dziewiątego": 9,
    "dziesiatego": 10,
    "dziesiątego": 10,
    "jedenastego": 11,
    "dwunastego": 12,
}


def _extract_current_count_from_planned_ordinal(text: str) -> str | None:
    """Wylicza stan aktualny z fraz typu: 'planujemy budowę dwunastego magazynu'."""
    lowered = text.lower()
    if not any(marker in lowered for marker in ["planuj", "wybudow", "budow", "powstanie"]):
        return None

    digit_match = re.search(
        r"(?:budow(?:a|ę|e|ac)?|wybudow(?:a|ac|ać)?).{0,80}?(\d+)(?:go|ego|tego)?\s+magazyn",
        lowered,
        re.IGNORECASE,
    )
    if digit_match:
        planned = int(digit_match.group(1))
        if planned > 0:
            return str(planned - 1)

    ordinal_pattern = "(" + "|".join(_POLISH_ORDINAL_WORDS.keys()) + ")"
    word_match = re.search(
        rf"(?:budow(?:a|ę|e|ac)?|wybudow(?:a|ac|ać)?).{{0,80}}?{ordinal_pattern}\s+magazyn",
        lowered,
        re.IGNORECASE,
    )
    if word_match:
        planned = _POLISH_ORDINAL_WORDS.get(word_match.group(1), 0)
        if planned > 0:
            return str(planned - 1)
    return None


def _extract_warehouses_count(text: str) -> str | None:
    """Wydobywa liczbę magazynów z tekstu (cyfry i słownie)."""
    lowered = text.lower()
    future_markers = [
        "planujemy",
        "na wiosn",
        "wybudow",
        "zbudow",
        "powstanie",
        "bedzie",
        "będzie",
        "docelowo",
    ]

    warehouse_patterns = [
        r"(?:liczba|ilosc|ilość|stan)\s+(?:magazyn(?:ow|ów|y)?)\D{0,20}(\d+)",
        r"(?:aktualnie|obecnie)?\D{0,15}(?:magazyn(?:ow|ów|y)?)\D{0,20}(\d+)",
        r"(\d+)\D{0,20}(?:magazyn(?:ow|ów|y)?)",
        r"(?:na\s+syjonie\s+jest)\D{0,20}(\d+)\D{0,10}(?:magazyn|magazyny|magazynow|magazynów)",
    ]
    for pattern in warehouse_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        left = max(0, match.start() - 80)
        right = min(len(lowered), match.end() + 40)
        context = lowered[left:right]
        if any(marker in context for marker in future_markers):
            continue
        return match.group(1)

    inferred_from_plan = _extract_current_count_from_planned_ordinal(text)
    if inferred_from_plan is not None:
        return inferred_from_plan

    word_pattern = r"(zero|jedenascie|jedenaście|dwanascie|dwanaście|dziesiec|dziesięć|dziewiec|dziewięć|osiem|siedem|szesc|sześć|piec|pięć|cztery|trzy|dwie|dwa|jedna|jedno|jeden)"
    words_match = re.search(
        rf"(?:liczba|ilosc|ilość|stan)?\D{{0,15}}(?:magazyn(?:ow|ów|y)?)\D{{0,15}}{word_pattern}",
        lowered,
        re.IGNORECASE,
    )
    if words_match:
        left = max(0, words_match.start() - 80)
        right = min(len(lowered), words_match.end() + 40)
        context = lowered[left:right]
        if any(marker in context for marker in future_markers):
            return None
        return str(_POLISH_NUMBER_WORDS.get(words_match.group(1), ""))
    return None


def extract_facts_with_regex(text: str) -> dict[str, Any]:
    """Probuje wydobyc docelowe fakty prostymi regulami regex.

    Args:
        text: Transkrypcja do analizy.

    Returns:
        Slownik z opcjonalnymi polami cityName, cityArea, warehousesCount, phoneNumber.
    """
    city_name = None
    city_area = None
    warehouses_count = None
    phone_number = None

    city_match = re.search(r"(Syjon|[A-Z][A-Za-z\-]{2,})", text)
    if city_match:
        city_name = city_match.group(1)

    area_match = re.search(r"(\d+[.,]\d+|\d+)\s*(km2|km\^2|km2)", text, re.IGNORECASE)
    if area_match:
        city_area = area_match.group(1).replace(",", ".")

    warehouses_count = _extract_warehouses_count(text)

    phone_match = re.search(r"\b(?:\+48\s*)?(\d{9})\b", text)
    if phone_match:
        phone_number = phone_match.group(1)

    return {
        "cityName": city_name,
        "cityArea": city_area,
        "warehousesCount": warehouses_count,
        "phoneNumber": phone_number,
    }
