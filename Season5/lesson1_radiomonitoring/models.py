"""Modele danych używane w aplikacji radiomonitoring."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional

from pydantic import BaseModel, Field


class CentralaRequest(BaseModel):
    """Reprezentuje żądanie wysyłane do endpointu /verify."""

    apikey: str
    task: str
    answer: dict[str, Any]


class ListenResponse(BaseModel):
    """Reprezentuje odpowiedź nasłuchu zwracaną przez Centralę."""

    code: int
    message: str
    transcription: Optional[str] = None
    meta: Optional[str] = None
    attachment: Optional[str] = None
    filesize: Optional[int] = None


class CandidateFact(BaseModel):
    """Przechowuje potencjalną wartość pola wraz ze źródłem i pewnością."""

    field_name: str
    value: str
    confidence: float = 0.0
    source: str = "unknown"


class FinalReport(BaseModel):
    """Reprezentuje finalny raport wysyłany w akcji transmit."""

    action: str = "transmit"
    cityName: str
    cityArea: str
    warehousesCount: int
    phoneNumber: str

    @staticmethod
    def format_city_area(value: str | float | Decimal) -> str:
        """Zaokrągla pole cityArea matematycznie do dwóch miejsc po przecinku.

        Args:
            value: Wartość wejściowa powierzchni miasta.

        Returns:
            Sformatowaną wartość z dokładnie dwoma miejscami po przecinku.
        """
        decimal_value = Decimal(str(value)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return f"{decimal_value:.2f}"
