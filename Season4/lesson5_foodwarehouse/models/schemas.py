"""Modele danych używane w aplikacji."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class VerifyRequest(BaseModel):
    """Reprezentuje payload wysyłany do endpointu /verify.

    Args:
        apikey: Klucz API użytkownika.
        task: Nazwa zadania.
        answer: Obiekt komendy narzędzia.
    """

    apikey: str
    task: str
    answer: dict[str, Any]


class VerifyResponse(BaseModel):
    """Reprezentuje odpowiedź zwracaną przez endpoint /verify.

    Args:
        code: Kod statusu biznesowego odpowiedzi.
        message: Komunikat zwrotny.
        data: Dodatkowe dane odpowiedzi.
    """

    code: int | None = None
    message: str | None = None
    data: Any = None
    model_config = ConfigDict(extra="allow")


class CityDemand(BaseModel):
    """Opisuje zapotrzebowanie pojedynczego miasta.

    Args:
        city: Nazwa miasta.
        destination: Kod destination wymagany przez API zamówień.
        items: Słownik towar -> ilość.
    """

    city: str
    destination: str | int | None = None
    items: dict[str, int] = Field(default_factory=dict)


class OrderContext(BaseModel):
    """Przechowuje dane potrzebne do utworzenia pojedynczego zamówienia.

    Args:
        city: Nazwa miasta.
        destination: Kod destination dla miasta.
        creator_id: Id użytkownika tworzącego zamówienie.
        signature: Podpis SHA1 zwrócony przez API.
        items: Towary i ilości do dopisania.
    """

    city: str
    destination: str
    creator_id: int
    signature: str
    items: dict[str, int]
