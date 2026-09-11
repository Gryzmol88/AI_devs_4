"""Narzędzia normalizacji tekstu dla nazw miast i przedmiotów."""

from __future__ import annotations

import re
import unicodedata


def normalize_text(value: str) -> str:
    """Normalizuje tekst do postaci pomocnej przy dopasowaniach.

    Args:
        value: Oryginalna wartość tekstowa.

    Returns:
        Tekst bez diakrytyków i znaków specjalnych, zapisany małymi literami.
    """

    text = value.strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def unique_preserve_order(values: list[str]) -> list[str]:
    """Usuwa duplikaty z listy zachowując kolejność wystąpień.

    Args:
        values: Lista wejściowych wartości.

    Returns:
        Lista bez duplikatów w kolejności pierwszego wystąpienia.
    """

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

