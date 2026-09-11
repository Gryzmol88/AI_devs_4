"""Modele danych dla logiki rozmowy i odpowiedzi API."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DialogState(str, Enum):
    """Opisuje etapy rozmowy z operatorem."""

    INTRO = "intro"
    ASK_ROADS = "ask_roads"
    REQUEST_DISABLE = "request_disable"
    ANSWER_QUESTION = "answer_question"
    FINISH = "finish"


class HubResponse(BaseModel):
    """Reprezentuje odpowiedź centrali na pojedynczy krok dialogu.

    Atrybuty:
        raw: Oryginalna odpowiedź JSON z API.
        text: Tekst odpowiedzi, jeśli dostępny.
        audio_base64: Odpowiedź audio zakodowana w base64, jeśli dostępna.
        done: Informacja, czy rozmowa została zakończona.
    """

    raw: dict[str, Any]
    text: str | None = None
    audio_base64: str | None = None
    done: bool = False


class StepSnapshot(BaseModel):
    """Przechowuje dane diagnostyczne jednego kroku dialogu.

    Atrybuty:
        step: Numer kroku.
        state: Stan maszyny stanów przed wykonaniem kroku.
        outbound_text: Wypowiedź tekstowa przygotowana przez agenta.
        inbound_text: Odczytana odpowiedź operatora.
        selected_road: Aktualnie wybrana droga do odblokowania.
    """

    step: int
    state: DialogState
    outbound_text: str
    inbound_text: str | None = None
    selected_road: str | None = None

