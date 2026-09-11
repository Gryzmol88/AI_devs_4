"""Modele domenowe i transportowe dla zadania filesystem."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ItemAmount(BaseModel):
    """Reprezentuje zapotrzebowanie miasta na dany towar.

    Atrybuty:
        item: Nazwa towaru.
        amount: Liczba potrzebnych sztuk bez jednostek.
    """

    item: str = Field(min_length=1)
    amount: int = Field(ge=0)


class CityNeed(BaseModel):
    """Reprezentuje miasto oraz jego potrzeby zakupowe.

    Atrybuty:
        name: Nazwa miasta.
        needs: Lista towarów i ilości potrzebnych dla miasta.
    """

    name: str = Field(min_length=1)
    needs: list[ItemAmount] = Field(default_factory=list)


class PersonRole(BaseModel):
    """Reprezentuje osobę odpowiedzialną za handel w mieście.

    Atrybuty:
        full_name: Imię i nazwisko osoby.
        city: Nazwa miasta zarządzanego przez osobę.
    """

    full_name: str = Field(min_length=1)
    city: str = Field(min_length=1)


class Offer(BaseModel):
    """Reprezentuje towar oferowany na sprzedaż przez miasto.

    Atrybuty:
        item: Nazwa towaru.
        city: Nazwa miasta oferującego towar.
    """

    item: str = Field(min_length=1)
    city: str = Field(min_length=1)


class ExtractedKnowledge(BaseModel):
    """Reprezentuje dane wyciągnięte z notatek Natana przez model LLM.

    Atrybuty:
        cities: Lista miast i ich potrzeb.
        people: Lista osób odpowiedzialnych za handel.
        offers: Lista towarów na sprzedaż.
        notes: Dodatkowa notatka diagnostyczna.
    """

    cities: list[CityNeed] = Field(default_factory=list)
    people: list[PersonRole] = Field(default_factory=list)
    offers: list[Offer] = Field(default_factory=list)
    notes: str = ""


class NormalizedKnowledge(BaseModel):
    """Reprezentuje dane po normalizacji nazw i deduplikacji.

    Atrybuty:
        city_needs: Mapa miasta na mapę potrzeb (`towar -> ilość`).
        person_to_city: Mapa osoby na miasto.
        person_display_name: Mapa identyfikatora osoby na pełną nazwę do treści pliku.
        item_to_cities: Mapa towaru na listę miast oferujących.
    """

    city_needs: dict[str, dict[str, int]] = Field(default_factory=dict)
    person_to_city: dict[str, str] = Field(default_factory=dict)
    person_display_name: dict[str, str] = Field(default_factory=dict)
    item_to_cities: dict[str, list[str]] = Field(default_factory=dict)


class FsAction(BaseModel):
    """Reprezentuje pojedynczą akcję API wykonywaną na wirtualnym filesystemie.

    Atrybuty:
        action: Nazwa akcji API, np. `createDir` lub `createFile`.
        path: Ścieżka docelowa akcji.
        content: Opcjonalna zawartość pliku.
    """

    action: str = Field(min_length=1)
    path: str = Field(min_length=1)
    content: str | None = None

    def to_payload(self) -> dict[str, str]:
        """Konwertuje model do formatu zgodnego z API verify.

        Returns:
            dict[str, str]: Słownik gotowy do osadzenia w polu `answer`.
        """

        payload: dict[str, str] = {"action": self.action, "path": self.path}
        if self.content is not None:
            payload["content"] = self.content
        return payload
