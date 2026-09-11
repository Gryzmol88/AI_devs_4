from typing import Any

from ..config import Settings
from ..models import VerifyPayload
from .retry import request_json


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class HubClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def fetch_power_plants(self) -> list[dict]:
        raw = request_json("GET", self.settings.locations_url)

        items = raw if isinstance(raw, list) else raw.get("items", [])
        out: list[dict] = []

        for item in items:
            code = item.get("code") or item.get("powerPlant") or item.get("id")
            lat = _float_or_none(item.get("lat") or item.get("latitude"))
            lon = _float_or_none(item.get("lon") or item.get("lng") or item.get("longitude"))
            if code and lat is not None and lon is not None:
                out.append({"code": str(code), "lat": lat, "lon": lon})
        return out

    def fetch_person_locations(self, name: str, surname: str) -> list[dict]:
        url = f"{self.settings.HUB_BASE_URL}/api/location"
        payload = {"apikey": self.settings.hub_api_key, "name": name, "surname": surname}
        raw = request_json("POST", url, json=payload)

        items = raw if isinstance(raw, list) else raw.get("locations", raw.get("result", []))
        out: list[dict] = []
        for item in items:
            lat = _float_or_none(item.get("lat") or item.get("latitude"))
            lon = _float_or_none(item.get("lon") or item.get("lng") or item.get("longitude"))
            if lat is not None and lon is not None:
                out.append({"lat": lat, "lon": lon})
        return out

    def fetch_access_level(self, name: str, surname: str, birth_year: int) -> int:
        url = f"{self.settings.HUB_BASE_URL}/api/accesslevel"
        payload = {
            "apikey": self.settings.hub_api_key,
            "name": name,
            "surname": surname,
            "birthYear": int(birth_year),
        }
        raw = request_json("POST", url, json=payload)

        if isinstance(raw, dict):
            value = raw.get("accessLevel", raw.get("access_level"))
            if isinstance(value, int):
                return value
        raise ValueError(f"Unexpected accesslevel response: {raw}")

    def verify_findhim(self, *, name: str, surname: str, access_level: int, power_plant: str) -> dict:
        payload = VerifyPayload(
            apikey=self.settings.hub_api_key,
            answer={
                "name": name,
                "surname": surname,
                "accessLevel": int(access_level),
                "powerPlant": power_plant,
            },
        )
        return request_json("POST", self.settings.VERIFY_URL, json=payload.model_dump())

