import json
from pathlib import Path
from typing import Any

from ..api.hub_client import HubClient
from ..config import Settings
from ..geo import nearest_plant
from ..models import Coordinates, Person, PowerPlant


class ToolHandlers:
    def __init__(self, settings: Settings, hub: HubClient, suspects: list[Person], plants: list[PowerPlant]):
        self.settings = settings
        self.hub = hub
        self.suspects = suspects
        self.plants = plants

    def get_suspects(self, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "count": len(self.suspects),
            "items": [
                {"name": s.name, "surname": s.surname, "birthYear": s.birth_year} for s in self.suspects
            ],
        }

    def analyze_suspect(self, args: dict[str, Any]) -> dict[str, Any]:
        name = str(args["name"]).strip()
        surname = str(args["surname"]).strip()
        birth_year = int(args["birthYear"])

        points_raw = self.hub.fetch_person_locations(name=name, surname=surname)
        points = [Coordinates(lat=float(p["lat"]), lon=float(p["lon"])) for p in points_raw]
        plant, distance_km = nearest_plant(points, self.plants)

        return {
            "name": name,
            "surname": surname,
            "birthYear": birth_year,
            "powerPlant": plant.code,
            "distanceKm": round(distance_km, 3),
            "isCandidate": distance_km <= self.settings.DISTANCE_THRESHOLD_KM,
        }

    def get_access_level(self, args: dict[str, Any]) -> dict[str, Any]:
        access_level = self.hub.fetch_access_level(
            name=str(args["name"]).strip(),
            surname=str(args["surname"]).strip(),
            birth_year=int(args["birthYear"]),
        )
        return {"accessLevel": access_level}

    def submit_findhim_answer(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.hub.verify_findhim(
            name=str(args["name"]).strip(),
            surname=str(args["surname"]).strip(),
            access_level=int(args["accessLevel"]),
            power_plant=str(args["powerPlant"]).strip(),
        )

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "get_suspects":
                return {"ok": True, "data": self.get_suspects(args)}
            if name == "analyze_suspect":
                return {"ok": True, "data": self.analyze_suspect(args)}
            if name == "get_access_level":
                return {"ok": True, "data": self.get_access_level(args)}
            if name == "submit_findhim_answer":
                return {"ok": True, "data": self.submit_findhim_answer(args)}
            return {"ok": False, "error": f"Unknown tool: {name}"}
        except Exception as error:  # noqa: BLE001
            return {
                "ok": False,
                "error": str(error),
                "hint": "Fix arguments or choose another tool.",
            }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

