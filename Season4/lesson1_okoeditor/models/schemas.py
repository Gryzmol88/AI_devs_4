"""Modele danych wykorzystywane przez aplikację."""

from typing import Any

from pydantic import BaseModel, Field


class VerifyRequest(BaseModel):
    """Definiuje payload wysyłany do endpointu `/verify`.

    Atrybuty:
        apikey: Klucz API użytkownika.
        task: Nazwa realizowanego zadania.
        answer: Treść akcji i jej parametry.
    """

    apikey: str
    task: str
    answer: dict[str, Any]


class ApiActionSnapshot(BaseModel):
    """Przechowuje zapis pojedynczej akcji wysłanej do API.

    Atrybuty:
        action_name: Nazwa wykonanej akcji.
        payload: Payload przekazany do API.
        response: Odpowiedź otrzymana z API.
        ok: Flaga sukcesu technicznego akcji.
    """

    action_name: str
    payload: dict[str, Any] = Field(default_factory=dict)
    response: dict[str, Any] = Field(default_factory=dict)
    ok: bool = True


class RunSummary(BaseModel):
    """Zawiera podsumowanie przebiegu wykonania zadania.

    Atrybuty:
        steps: Lista snapshotów wykonanych akcji.
        final_response: Odpowiedź otrzymana dla akcji `done`.
    """

    steps: list[ApiActionSnapshot] = Field(default_factory=list)
    final_response: dict[str, Any] = Field(default_factory=dict)

