"""Modele domenowe używane w pipeline ewaluacji."""

from __future__ import annotations

from typing import Dict, List, Literal, Set

from pydantic import BaseModel, Field


FIELD_TO_SENSOR_TYPE: Dict[str, str] = {
    "temperature_K": "temperature",
    "pressure_bar": "pressure",
    "water_level_meters": "water",
    "voltage_supply_v": "voltage",
    "humidity_percent": "humidity",
}


class SensorRecord(BaseModel):
    """Pojedynczy odczyt sensora wczytany z pliku JSON.

    Attributes:
        file_id: Identyfikator pliku, zwykle nazwa pliku bez rozszerzenia.
        sensor_type: Aktywny sensor lub sensory rozdzielone znakiem "/".
        timestamp: Unixowy znacznik czasu pomiaru.
        temperature_K: Wartość temperatury w kelwinach.
        pressure_bar: Wartość ciśnienia w barach.
        water_level_meters: Wartość poziomu wody w metrach.
        voltage_supply_v: Wartość napięcia w woltach.
        humidity_percent: Wartość wilgotności w procentach.
        operator_notes: Notatka operatora.
    """

    file_id: str
    sensor_type: str
    timestamp: int
    temperature_K: float
    pressure_bar: float
    water_level_meters: float
    voltage_supply_v: float
    humidity_percent: float
    operator_notes: str

    def active_sensor_types(self) -> Set[str]:
        """Zwraca znormalizowane nazwy aktywnych sensorów z pola sensor_type."""
        return {item.strip().lower() for item in self.sensor_type.split("/") if item.strip()}


class RuleAnomaly(BaseModel):
    """Reprezentuje anomalie wykryte regułami deterministycznymi.

    Attributes:
        file_id: Identyfikator pliku z anomalią.
        reasons: Lista powodów wykrycia anomalii.
    """

    file_id: str
    reasons: List[str] = Field(default_factory=list)


class NoteAssessment(BaseModel):
    """Wynik klasyfikacji pojedynczej notatki operatora.

    Attributes:
        note: Oryginalny tekst notatki.
        stance: Zinterpretowana postawa notatki: ok/anomaly/uncertain.
        confidence: Współczynnik pewności od 0.0 do 1.0.
        source: Źródło klasyfikacji (llm/heuristic).
    """

    note: str
    stance: Literal["ok", "anomaly", "uncertain"]
    confidence: float
    source: Literal["llm", "heuristic"]


class FinalResult(BaseModel):
    """Model finalnego payloadu oczekiwanego przez endpoint weryfikacyjny.

    Attributes:
        apikey: Klucz API akceptowany przez API weryfikacji.
        task: Nazwa zadania.
        answer: Słownik zawierający listę identyfikatorów recheck.
    """

    apikey: str
    task: str
    answer: Dict[str, List[str]]
