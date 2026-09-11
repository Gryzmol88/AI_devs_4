"""Algorytm planowania harmonogramu turbiny windpower."""

from __future__ import annotations

import re
from datetime import datetime
from datetime import timedelta
from typing import Any

from models.schemas import ConfigPoint
from models.schemas import PlanningContext
from models.schemas import PlanningResult
from models.schemas import WindDataPoint


class WindPlanner:
    """Wylicza konfiguracje ochrony i produkcji na podstawie raportow."""

    def build_context(self, reports: dict[str, dict[str, Any]]) -> PlanningContext:
        """Buduje kontekst planowania z surowych raportow API.

        Args:
            reports: Raporty odebrane z API.

        Returns:
            Obiekt PlanningContext z gotowymi danymi wejscia.

        Raises:
            ValueError: Gdy nie da sie odczytac podstawowych danych.
        """

        weather_payload = self._find_payload(
            reports=reports,
            key_candidates=("weather", "forecast", "wind", "weatherReport"),
        )
        turbine_payload = self._find_payload(
            reports=reports,
            key_candidates=("turbine", "turbineInfo", "device", "spec"),
        )
        demand_payload = self._find_payload(
            reports=reports,
            key_candidates=("power", "demand", "deficit", "energy"),
        )
        documentation_payload = self._find_payload(
            reports=reports,
            key_candidates=("documentation", "docs", "manual", "instruction"),
        )

        weather_points = self._parse_weather_points(weather_payload=weather_payload)
        if not weather_points:
            raise ValueError("Brak danych pogodowych potrzebnych do planowania.")

        wind_limit = self._extract_float(
            payload=turbine_payload,
            candidates=("maxSafeWind", "windLimit", "maxWindSpeed", "safeWindSpeed"),
            fallback=self._extract_wind_limit_from_docs(
                payload=documentation_payload,
                fallback=20.0,
            ),
        )
        missing_power = self._extract_float(
            payload=demand_payload,
            candidates=("missingPower", "requiredPower", "deficitPower", "powerDeficit"),
            fallback=self._extract_range_high(
                payload=demand_payload,
                candidates=("powerDeficitKw", "missingPowerKw", "requiredPowerKw"),
                fallback=1.0,
            ),
        )
        return PlanningContext(
            weather_points=sorted(weather_points, key=lambda item: item.timestamp),
            turbine_wind_limit=wind_limit,
            missing_power=missing_power,
        )

    def plan(self, context: PlanningContext) -> PlanningResult:
        """Wyznacza harmonogram ochronny i pierwszy punkt produkcji.

        Args:
            context: Kontekst z danymi o pogodzie, limicie i zapotrzebowaniu.

        Returns:
            Wynik planowania zawierajacy wszystkie punkty konfiguracji.

        Raises:
            ValueError: Gdy nie ma bezpiecznego okna produkcji.
        """

        notes: list[str] = []
        configs: list[ConfigPoint] = []

        storms: list[WindDataPoint] = [
            item for item in context.weather_points if item.wind_speed > context.turbine_wind_limit
        ]
        notes.append(f"Wykryto {len(storms)} zdarzen sztormowych.")

        for storm in storms:
            protective_time = self._floor_to_hour(storm.timestamp)
            configs.append(
                ConfigPoint(
                    timestamp=protective_time,
                    wind_ms=storm.wind_speed,
                    pitch_angle=90,
                    turbine_mode="idle",
                    reason="Ochrona lopat podczas wichury.",
                )
            )

        production_candidates: list[ConfigPoint] = []
        for point in context.weather_points:
            if point.wind_speed > context.turbine_wind_limit:
                continue
            if point.wind_speed < 4.0:
                continue
            if self._is_hour_after_storm(point=point, storms=storms):
                continue

            best_pitch = self._select_best_pitch(wind_speed=point.wind_speed)
            produced_power = self._estimate_generated_power_kw(
                wind_speed=point.wind_speed,
                pitch_angle=best_pitch,
                cutoff_wind=context.turbine_wind_limit,
            )
            if produced_power < context.missing_power:
                continue
            production_candidates.append(
                ConfigPoint(
                    timestamp=self._floor_to_hour(point.timestamp),
                    wind_ms=point.wind_speed,
                    pitch_angle=best_pitch,
                    turbine_mode="production",
                    reason="Pierwsze bezpieczne okno produkcji brakujacej mocy.",
                )
            )

        if not production_candidates:
            raise ValueError("Nie znaleziono bezpiecznego okna produkcji.")

        production_candidates.sort(key=lambda item: item.timestamp)
        production_point = production_candidates[0]
        configs.append(production_point)

        merged_configs = self._deduplicate_configs(configs=configs)
        merged_configs.sort(key=lambda item: item.timestamp)
        notes.append(f"Liczba punktow konfiguracji: {len(merged_configs)}.")

        return PlanningResult(
            configs=merged_configs,
            production_point=production_point,
            notes=notes,
        )

    @staticmethod
    def _find_payload(
        reports: dict[str, dict[str, Any]],
        key_candidates: tuple[str, ...],
    ) -> dict[str, Any]:
        """Wyszukuje najbardziej pasujacy payload w raportach.

        Args:
            reports: Zbior raportow.
            key_candidates: Kandydaci nazw kluczy dla raportu.

        Returns:
            Wybrany payload jako slownik.
        """

        lowered = {name.lower(): data for name, data in reports.items()}
        for candidate in key_candidates:
            if candidate.lower() in lowered:
                return WindPlanner._unwrap_response_payload(lowered[candidate.lower()])
        for data in reports.values():
            for candidate in key_candidates:
                value = data.get(candidate)
                if isinstance(value, dict):
                    return WindPlanner._unwrap_response_payload(value)
        for data in reports.values():
            if isinstance(data, dict):
                return WindPlanner._unwrap_response_payload(data)
        return {}

    @staticmethod
    def _unwrap_response_payload(payload: dict[str, Any]) -> dict[str, Any]:
        """Usuwa otoczke odpowiedzi API i zwraca glowny payload danych.

        Args:
            payload: Pelna odpowiedz API lub fragment danych.

        Returns:
            Slownik z docelowymi danymi raportu.
        """

        current = payload
        for key in ("result", "data", "report", "payload"):
            nested = current.get(key)
            if isinstance(nested, dict) and nested:
                current = nested
        return current

    def _parse_weather_points(self, weather_payload: dict[str, Any]) -> list[WindDataPoint]:
        """Parsuje rekordy pogody z roznorodnych formatow API.

        Args:
            weather_payload: Raport pogodowy lub jego fragment.

        Returns:
            Lista punktow pogody.
        """

        arrays: list[list[Any]] = []
        stack: list[Any] = [weather_payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for key, value in current.items():
                    if key in {"forecast", "weather", "points", "hours", "data", "result"} and isinstance(value, list):
                        arrays.append(value)
                    elif isinstance(value, dict):
                        stack.append(value)
                    elif isinstance(value, list) and value and isinstance(value[0], dict):
                        arrays.append(value)

        points: list[WindDataPoint] = []
        for data_array in arrays:
            for item in data_array:
                if not isinstance(item, dict):
                    continue
                timestamp = self._extract_datetime(
                    item=item,
                    candidates=("timestamp", "time", "datetime", "date"),
                )
                wind_speed = self._extract_float(
                    payload=item,
                    candidates=("windMs", "wind", "windSpeed", "wind_speed", "speed"),
                    fallback=-1.0,
                )
                if timestamp is None or wind_speed < 0:
                    continue
                points.append(WindDataPoint(timestamp=timestamp, wind_speed=wind_speed, raw=item))
        return points

    @staticmethod
    def _extract_datetime(item: dict[str, Any], candidates: tuple[str, ...]) -> datetime | None:
        """Odczytuje datetime z rekordu na podstawie listy kluczy.

        Args:
            item: Rekord z danymi.
            candidates: Nazwy kluczy potencjalnie przechowujacych datetime.

        Returns:
            Sparsowany datetime lub None.
        """

        for key in candidates:
            value = item.get(key)
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
                except ValueError:
                    continue
        return None

    @staticmethod
    def _extract_float(payload: dict[str, Any], candidates: tuple[str, ...], fallback: float) -> float:
        """Odczytuje wartosc numeryczna z payloadu.

        Args:
            payload: Slownik z danymi.
            candidates: Nazwy kluczy do sprawdzenia.
            fallback: Wartosc domyslna.

        Returns:
            Odczytana liczba zmiennoprzecinkowa lub fallback.
        """

        for key in candidates:
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        for value in payload.values():
            if isinstance(value, dict):
                nested = WindPlanner._extract_float(payload=value, candidates=candidates, fallback=fallback)
                if nested != fallback:
                    return nested
        return fallback

    @staticmethod
    def _extract_wind_limit_from_docs(payload: dict[str, Any], fallback: float) -> float:
        """Wydobywa limit bezpiecznego wiatru z dokumentacji tekstowej.

        Args:
            payload: Slownik dokumentacji zwrocony przez API.
            fallback: Wartosc domyslna, gdy brak danych.

        Returns:
            Odczytany limit wiatru lub fallback.
        """

        direct_cutoff = WindPlanner._extract_float(
            payload=payload,
            candidates=("cutoffWindMs", "cutoffWind", "shutdownWindMs"),
            fallback=-1.0,
        )
        if direct_cutoff > 0:
            return direct_cutoff

        texts: list[str] = []
        stack: list[Any] = [payload]
        while stack:
            current = stack.pop()
            if isinstance(current, dict):
                for value in current.values():
                    stack.append(value)
            elif isinstance(current, list):
                for value in current:
                    stack.append(value)
            elif isinstance(current, str):
                texts.append(current)

        text_blob = " ".join(texts)
        patterns = [
            r"(?:max(?:imum)?\s*wind|wind\s*limit|safe\s*wind)[^\d]{0,25}(\d+(?:[.,]\d+)?)",
            r"(?:wytrzymalos\w*|limit\w*\s*wiatr\w*)[^\d]{0,25}(\d+(?:[.,]\d+)?)",
            r"(\d+(?:[.,]\d+)?)\s*m\/s",
        ]
        for pattern in patterns:
            match = re.search(pattern, text_blob, flags=re.IGNORECASE)
            if match:
                value = match.group(1).replace(",", ".")
                try:
                    parsed = float(value)
                    if parsed > 0:
                        return parsed
                except ValueError:
                    continue
        return fallback

    @staticmethod
    def _select_best_pitch(wind_speed: float) -> int:
        """Wybiera kat lopat dajacy najwyzsza produkcje energii.

        Args:
            wind_speed: Predkosc wiatru dla rozpatrywanej godziny.

        Returns:
            Kat lopat 0 lub 45 stopni.
        """

        power_pitch_0 = WindPlanner._estimate_generated_power_kw(
            wind_speed=wind_speed,
            pitch_angle=0,
            cutoff_wind=14.0,
        )
        power_pitch_45 = WindPlanner._estimate_generated_power_kw(
            wind_speed=wind_speed,
            pitch_angle=45,
            cutoff_wind=14.0,
        )
        return 0 if power_pitch_0 >= power_pitch_45 else 45

    @staticmethod
    def _estimate_generated_power_kw(wind_speed: float, pitch_angle: int, cutoff_wind: float) -> float:
        """Szacuje produkowana moc na podstawie dokumentacji turbiny.

        Args:
            wind_speed: Predkosc wiatru w m/s.
            pitch_angle: Kat lopat (0, 45, 90).
            cutoff_wind: Prog odciecia (brak produkcji powyzej progu).

        Returns:
            Szacowana moc produkowana w kW.
        """

        rated_power_kw = 14.0
        if wind_speed < 4.0 or wind_speed >= cutoff_wind:
            return 0.0

        # Mediany zakresow yieldPercent z dokumentacji.
        anchors = [
            (4.0, 12.5),
            (6.0, 35.0),
            (8.0, 65.0),
            (10.0, 95.0),
            (12.0, 100.0),
        ]
        yield_percent = 100.0
        for idx in range(len(anchors) - 1):
            x1, y1 = anchors[idx]
            x2, y2 = anchors[idx + 1]
            if x1 <= wind_speed <= x2:
                ratio = (wind_speed - x1) / (x2 - x1)
                yield_percent = y1 + ratio * (y2 - y1)
                break
            if wind_speed < x1:
                yield_percent = y1
                break

        pitch_multiplier = 1.0
        if pitch_angle == 45:
            pitch_multiplier = 0.65
        elif pitch_angle == 90:
            pitch_multiplier = 0.0

        return rated_power_kw * (yield_percent / 100.0) * pitch_multiplier

    @staticmethod
    def _extract_range_high(payload: dict[str, Any], candidates: tuple[str, ...], fallback: float) -> float:
        """Odczytuje gorna granice liczby z wartosci tekstowej, np. "3-4".

        Args:
            payload: Slownik z danymi.
            candidates: Nazwy kluczy do sprawdzenia.
            fallback: Wartosc domyslna.

        Returns:
            Gorna granica zakresu albo fallback.
        """

        for key in candidates:
            value = payload.get(key)
            if isinstance(value, str):
                cleaned = value.replace(",", ".").strip()
                if "-" in cleaned:
                    parts = [item.strip() for item in cleaned.split("-") if item.strip()]
                    if parts:
                        try:
                            return float(parts[-1])
                        except ValueError:
                            pass
                try:
                    return float(cleaned)
                except ValueError:
                    continue
        return fallback

    @staticmethod
    def _floor_to_hour(moment: datetime) -> datetime:
        """Zaokragla czas do pelnej godziny.

        Args:
            moment: Oryginalny znacznik czasu.

        Returns:
            Datetime z minutami i sekundami rownymi 0.
        """

        return moment.replace(minute=0, second=0, microsecond=0)

    def _is_hour_after_storm(self, point: WindDataPoint, storms: list[WindDataPoint]) -> bool:
        """Sprawdza, czy punkt czasu jest okolo godzine po wichurze.

        Args:
            point: Kandydat na punkt produkcji.
            storms: Lista punktow sztormowych.

        Returns:
            True, jesli punkt wpada w przedzial ochronny po wichurze.
        """

        for storm in storms:
            delta = point.timestamp - storm.timestamp
            if timedelta(0) <= delta <= timedelta(hours=1):
                return True
        return False

    @staticmethod
    def _deduplicate_configs(configs: list[ConfigPoint]) -> list[ConfigPoint]:
        """Usuwa duplikaty konfiguracji, zachowujac ostatni wpis dla godziny.

        Args:
            configs: Lista punktow konfiguracji.

        Returns:
            Lista bez duplikatow godzin.
        """

        dedup: dict[str, ConfigPoint] = {}
        for config in configs:
            dedup[config.as_payload_key()] = config
        return list(dedup.values())
