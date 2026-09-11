"""Schematy Pydantic używane w przepływie analizy mapy."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class CoordinateResult(BaseModel):
    """Reprezentuje końcowy wynik analizy mapy dla kolejnego etapu misji.

    Pola:
    - `col`: kolumna sektora docelowego (indeks od 1),
    - `row`: wiersz sektora docelowego (indeks od 1),
    - `grid_cols`: wykryta liczba kolumn całej siatki,
    - `grid_rows`: wykryta liczba wierszy całej siatki,
    - `confidence`: pewność modelu w zakresie [0.0, 1.0],
    - `reasoning_short`: krótkie uzasadnienie w języku naturalnym.
    """

    col: int = Field(ge=1, description="Kolumna sektora docelowego, indeksowana od 1.")
    row: int = Field(ge=1, description="Wiersz sektora docelowego, indeksowany od 1.")
    grid_cols: int = Field(ge=1, description="Wykryta liczba kolumn siatki.")
    grid_rows: int = Field(ge=1, description="Wykryta liczba wierszy siatki.")
    confidence: float = Field(ge=0.0, le=1.0, description="Wskaźnik pewności modelu.")
    reasoning_short: str = Field(min_length=3, description="Krótkie uzasadnienie decyzji modelu.")

    @field_validator("reasoning_short")
    @classmethod
    def _normalize_reasoning(cls, value: str) -> str:
        """Normalizuje uzasadnienie do przyciętego tekstu jednoliniowego."""

        return " ".join(value.strip().split())


class DroneInstructionPlan(BaseModel):
    """Plan instrukcji drona wygenerowany przez agenta sterującego.

    Pola:
    - `instructions`: sekwencja instrukcji do wysłania w `answer.instructions`,
    - `reasoning_short`: krótkie uzasadnienie do logów/debugu.
    """

    instructions: list[str] = Field(min_length=1, description="Sekwencja instrukcji drona.")
    reasoning_short: str = Field(min_length=3, description="Krótkie uzasadnienie planu.")
