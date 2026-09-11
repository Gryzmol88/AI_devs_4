"""Agregacja i wybor finalnych wartosci wymaganych przez raport."""

from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from models import FinalReport


class FactAggregator:
    """Zbiera kandydatow i wyznacza finalny raport."""

    def __init__(self) -> None:
        """Tworzy pusty agregator faktow."""
        self._values: dict[str, list[str]] = defaultdict(list)
        self._scores: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    def add_candidate_dict(self, data: dict[str, Any], source: str) -> None:
        """Dodaje zestaw kandydatow z konkretnego zrodla.

        Args:
            data: Slownik potencjalnych wartosci pol.
            source: Nazwa zrodla danych (np. transcription, attachment, llm).
        """
        source_weight = self._source_weight(source)
        for field_name in ["cityName", "cityArea", "warehousesCount", "phoneNumber"]:
            value = data.get(field_name)
            if value is None:
                continue
            normalized = str(value).strip()
            if not normalized:
                continue
            if not self._is_valid_candidate(field_name, normalized):
                continue
            self._values[field_name].append(normalized)
            self._scores[field_name][normalized] += source_weight

    def _source_weight(self, source: str) -> int:
        """Zwraca wage wiarygodnosci dla konkretnego zrodla."""
        weights = {
            "attachment-local": 5,
            "attachment-nested": 4,
            "attachment-llm": 3,
            "attachment-vision-llm": 3,
            "attachment-vision-warehouses-llm": 4,
            "audio-transcription-regex": 2,
            "audio-transcription-llm": 1,
            "transcription-llm": 2,
            "transcription-regex": 1,
            "rescue-warehouses-llm": 3,
        }
        return weights.get(source, 1)

    def _is_valid_candidate(self, field_name: str, value: str) -> bool:
        """Sprawdza czy kandydat ma sensowny format dla danego pola."""
        if field_name == "cityArea":
            return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", value))
        if field_name == "warehousesCount":
            return bool(re.fullmatch(r"\d+", value))
        if field_name == "phoneNumber":
            only_digits = re.sub(r"\D", "", value)
            return len(only_digits) in {9, 11, 12}
        if field_name == "cityName":
            blacklist = {
                "png",
                "jfif",
                "utf-",
                "tsse",
                "sssssszzzzz",
                "tata",
                "chcesz",
                "sluchaj",
                "przede",
                "teraz",
                "miasto",
            }
            lowered = value.lower()
            if lowered in blacklist:
                return False
            return bool(re.fullmatch(r"[A-Za-z\-\s]{3,80}", value))
        return True

    def snapshot(self) -> dict[str, list[str]]:
        """Zwraca aktualny stan wszystkich zebranych kandydatow."""
        return dict(self._values)

    def _pick_most_frequent(self, field_name: str) -> str | None:
        """Wybiera kandydat oparty o laczna wage i czestotliwosc."""
        values = self._values.get(field_name, [])
        if not values:
            return None
        counts: dict[str, int] = {}
        for item in values:
            counts[item] = counts.get(item, 0) + 1
        ranked = sorted(
            counts.items(),
            key=lambda x: (
                self._scores.get(field_name, {}).get(x[0], 0),
                x[1],
                len(x[0]),
            ),
            reverse=True,
        )
        return ranked[0][0]

    def build_final_report(self) -> FinalReport:
        """Buduje finalny raport na podstawie zebranych kandydatow."""
        city_name = self._pick_most_frequent("cityName")
        city_area = self._pick_most_frequent("cityArea")
        warehouses_count = self._pick_most_frequent("warehousesCount")
        phone_number = self._pick_most_frequent("phoneNumber")

        missing = [
            name
            for name, value in {
                "cityName": city_name,
                "cityArea": city_area,
                "warehousesCount": warehouses_count,
                "phoneNumber": phone_number,
            }.items()
            if value is None
        ]
        if missing:
            raise ValueError(f"Brak wymaganych danych do raportu: {', '.join(missing)}")

        return FinalReport(
            cityName=str(city_name),
            cityArea=FinalReport.format_city_area(str(city_area)),
            warehousesCount=int(str(warehouses_count)),
            phoneNumber=re.sub(r"\D", "", str(phone_number))[-9:],
        )
