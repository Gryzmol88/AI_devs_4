"""Normalizacja odpowiedzi LLM do wspólnego formatu kandydatów faktów."""

from __future__ import annotations

from typing import Any


def normalize_llm_facts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalizuje odpowiedź LLM do listy słowników z polami raportu.

    Args:
        payload: Odpowiedź JSON z modelu.

    Returns:
        Lista kandydatów zawierających klucze cityName, cityArea,
        warehousesCount, phoneNumber.
    """
    expected_keys = {"cityName", "cityArea", "warehousesCount", "phoneNumber"}

    if expected_keys.intersection(payload.keys()):
        return [payload]

    if isinstance(payload.get("results"), list):
        normalized: list[dict[str, Any]] = []
        for item in payload["results"]:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "cityName": item.get("cityName"),
                        "cityArea": item.get("cityArea"),
                        "warehousesCount": item.get("warehousesCount"),
                        "phoneNumber": item.get("phoneNumber"),
                    }
                )
        return normalized

    if isinstance(payload.get("data"), list):
        normalized = []
        for item in payload["data"]:
            if isinstance(item, dict):
                normalized.append(
                    {
                        "cityName": item.get("cityName") or item.get("city_name"),
                        "cityArea": item.get("cityArea") or item.get("city_area"),
                        "warehousesCount": item.get("warehousesCount")
                        or item.get("warehouses_count"),
                        "phoneNumber": item.get("phoneNumber") or item.get("phone_number"),
                    }
                )
        return normalized

    return []
