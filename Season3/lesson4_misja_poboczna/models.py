"""Modele i funkcje pomocnicze do analizy odpowiedzi misji pobocznej."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


FLAG_REGEX = re.compile(r"\{FLG:[A-Za-z0-9_\-]+\}")


@dataclass(slots=True)
class AttemptResult:
    """Reprezentuje pojedynczą próbę wysłania payloadu do `/verify`.

    Atrybuty:
        attempt_index: Numer próby.
        label: Etykieta wariantu payloadu.
        payload: Wysłany payload JSON.
        response: Odebrana odpowiedź JSON.
        found_flag: Flaga znaleziona w odpowiedzi lub `None`.
        notes: Dodatkowe adnotacje diagnostyczne.
    """

    attempt_index: int
    label: str
    payload: dict[str, Any]
    response: dict[str, Any]
    found_flag: str | None
    notes: list[str] = field(default_factory=list)


def find_flag_in_payload(payload: Any) -> str | None:
    """Wyszukuje pierwszą flagę `{FLG:...}` w zagnieżdżonej strukturze.

    Args:
        payload: Dowolna struktura odpowiedzi.

    Returns:
        Znaleziona flaga albo `None`.
    """

    for value in walk_values(payload):
        if isinstance(value, str):
            match = FLAG_REGEX.search(value)
            if match:
                return match.group(0)
    return None


def walk_values(payload: Any) -> list[Any]:
    """Spłaszcza atomowe wartości z dowolnej struktury JSON.

    Args:
        payload: Struktura wejściowa.

    Returns:
        Lista wartości atomowych.
    """

    values: list[Any] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(walk_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(walk_values(item))
    else:
        values.append(payload)
    return values

