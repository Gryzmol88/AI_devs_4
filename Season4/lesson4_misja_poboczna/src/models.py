"""Modele danych dla eksploracji misji pobocznej."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProbeStep(BaseModel):
    """Reprezentuje pojedynczy krok eksploracji API.

    Atrybuty:
        id: Krótki identyfikator kroku.
        description: Opis celu kroku.
        answer: Pole `answer` wysyłane do verify.
    """

    id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    answer: dict


class ProbeResult(BaseModel):
    """Reprezentuje wynik wykonania pojedynczego kroku.

    Atrybuty:
        id: Id kroku.
        description: Opis kroku.
        ok: Informacja, czy HTTP zakończyło się sukcesem.
        response: Odpowiedź JSON API lub błąd tekstowy.
    """

    id: str
    description: str
    ok: bool
    response: dict

