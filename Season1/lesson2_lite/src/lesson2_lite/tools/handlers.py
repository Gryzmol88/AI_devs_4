import json
from pathlib import Path
from typing import Any

from ..api.hub_client import (
    extract_verify_code,
    fetch_access_level,
    fetch_person_locations,
    log_verify_attempt,
    submit_verify,
)
from ..geo import haversine_km, normalize_text


def write_json(path: Path, payload: Any) -> None:
    """
    Zapisuje dowolny obiekt jako JSON UTF-8 z wcieciami, tworzac brakujace foldery.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class ToolHandlers:
    """
    Grupuje logike wykonawcza narzedzi Function Calling i trzyma cache pomocniczy.
    """

    def __init__(
        self,
        *,
        api_key: str,
        suspects: list[dict[str, Any]],
        plants: list[dict[str, Any]],
    ):
        """
        Inicjalizuje stan handlera narzedzi i dane wejciowe agenta.
        """
        self.api_key = api_key
        self.suspects = suspects
        self.plants = plants
        self.city_coordinates: dict[str, tuple[float, float]] = {}
        self.expected_suspects = {
            (s["name"].strip().lower(), s["surname"].strip().lower(), int(s["birthYear"])) for s in suspects
        }
        self.analyzed_results: dict[tuple[str, str, int], dict[str, Any]] = {}

    def _missing_city_estimates(self) -> list[str]:
        """
        Zwraca liste miast elektrowni, dla ktorych brak estymacji wspolrzednych.
        """
        missing: list[str] = []
        for plant in self.plants:
            city = str(plant.get("city", "")).strip()
            if not city:
                continue
            if normalize_text(city) not in self.city_coordinates:
                missing.append(city)
        return sorted(set(missing))

    def get_suspects(self, _: dict[str, Any]) -> dict[str, Any]:
        """
        Zwraca komplet podejrzanych, aby model mogl po nich iterowac.
        """
        return {"count": len(self.suspects), "items": self.suspects}

    def get_power_plants(self, _: dict[str, Any]) -> dict[str, Any]:
        """
        Zwraca liste elektrowni (bez zbednych pol), zeby model widzial kody i miasta.
        """
        items = [
            {"code": p["code"], "city": p.get("city", ""), "isActive": p.get("isActive", True)}
            for p in self.plants
        ]
        return {"count": len(items), "items": items}

    def estimate_city_coordinates(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Rejestruje orientacyjne wspolrzedne miasta podane przez LLM.
        To narzedzie pozwala modelowi zamienic nazwe miasta elektrowni na lat/lon
        bez odpytywania zewnetrznego API geokodowania.
        """
        city = str(args["city"]).strip()
        lat = float(args["lat"])
        lon = float(args["lon"])
        if not city:
            raise ValueError("City cannot be empty")
        if lat < -90 or lat > 90:
            raise ValueError("Latitude out of range")
        if lon < -180 or lon > 180:
            raise ValueError("Longitude out of range")

        key = normalize_text(city)
        self.city_coordinates[key] = (lat, lon)
        return {"city": city, "lat": lat, "lon": lon, "saved": True}

    def analyze_suspect(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Analizuje jedna osobe: pobiera jej lokalizacje i porownuje je z orientacyjnymi
        wspolrzednymi miast elektrowni oszacowanymi przez LLM.
        """
        name = str(args["name"]).strip()
        surname = str(args["surname"]).strip()
        birth_year = int(args["birthYear"])
        print(f"[tool] analyze_suspect: start {name} {surname} ({birth_year})")
        locations = fetch_person_locations(self.api_key, name, surname)
        print(f"[tool] analyze_suspect: locations={len(locations)} for {name} {surname}")

        active_plants = [p for p in self.plants if p.get("isActive", True)]
        candidate_plants = active_plants if active_plants else self.plants
        missing_city_coords = [
            p["city"]
            for p in candidate_plants
            if normalize_text(str(p.get("city", ""))) not in self.city_coordinates
        ]
        if missing_city_coords:
            result = {
                "name": name,
                "surname": surname,
                "birthYear": birth_year,
                "hasLocations": False,
                "locationCount": len(locations),
                "missingCityCoordinates": sorted(set([c for c in missing_city_coords if c])),
                "hint": "Call estimate_city_coordinates for each missing city before analyze_suspect.",
            }
            self.analyzed_results[(name.strip().lower(), surname.strip().lower(), birth_year)] = result
            return result

        plant_stats: dict[str, dict[str, Any]] = {
            str(p["code"]): {"plant": p, "cityHits": 0, "minDistanceKm": float("inf")} for p in candidate_plants
        }

        for lat, lon in locations:
            for plant in candidate_plants:
                plant_code = str(plant["code"])
                city_key = normalize_text(str(plant.get("city", "")))
                estimated_coords = self.city_coordinates.get(city_key)
                if not estimated_coords:
                    continue
                city_lat, city_lon = estimated_coords
                distance = haversine_km(lat, lon, city_lat, city_lon)
                if distance < plant_stats[plant_code]["minDistanceKm"]:
                    plant_stats[plant_code]["minDistanceKm"] = distance
                if distance <= 10.0:
                    plant_stats[plant_code]["cityHits"] += 1

        key = (name.strip().lower(), surname.strip().lower(), birth_year)
        if not plant_stats:
            print(f"[tool] analyze_suspect: no result for {name} {surname}")
            result = {
                "name": name,
                "surname": surname,
                "birthYear": birth_year,
                "hasLocations": False,
                "locationCount": 0,
                "cityHits": 0,
            }
            self.analyzed_results[key] = result
            return result

        ranked_plants = sorted(
            [
                {
                    "code": code,
                    "cityHits": int(stats["cityHits"]),
                    "minDistanceKm": round(float(stats["minDistanceKm"]), 3),
                }
                for code, stats in plant_stats.items()
                if stats["minDistanceKm"] != float("inf")
            ],
            key=lambda x: (-x["cityHits"], float(x["minDistanceKm"])),
        )
        if not ranked_plants:
            result = {
                "name": name,
                "surname": surname,
                "birthYear": birth_year,
                "hasLocations": False,
                "locationCount": len(locations),
                "cityHits": 0,
            }
            self.analyzed_results[key] = result
            return result

        best_plant_code = str(ranked_plants[0]["code"])
        best_city_hits = int(ranked_plants[0]["cityHits"])
        best_distance = float(ranked_plants[0]["minDistanceKm"])

        result = {
            "name": name,
            "surname": surname,
            "birthYear": birth_year,
            "hasLocations": True,
            "locationCount": len(locations),
            "powerPlant": best_plant_code,
            "distanceKm": round(best_distance, 3),
            "cityHits": best_city_hits,
            "plantCandidates": ranked_plants,
        }
        print(
            "[tool] analyze_suspect: done "
            f"{name} {surname} -> plant={result['powerPlant']}, "
            f"distanceKm={result['distanceKm']}, cityHits={result['cityHits']}, "
            f"candidates={len(ranked_plants)}"
        )
        self.analyzed_results[key] = result
        return result

    def _best_candidate_from_analyzed(self) -> dict[str, Any] | None:
        """
        Zwraca najlepszego kandydata na podstawie kompletnych wynikow analiz.
        Kryterium glowne zgodne z trescia zadania: minimalna odleglosc distanceKm.
        """
        valid = [
            row
            for row in self.analyzed_results.values()
            if row.get("hasLocations") and isinstance(row.get("distanceKm"), (int, float))
        ]
        if not valid:
            return None
        return sorted(valid, key=lambda x: (-int(x.get("cityHits", 0)), float(x["distanceKm"])))[0]

    def _ranked_candidates_from_analyzed(self) -> list[dict[str, Any]]:
        """
        Zwraca kandydatow posortowanych rosnaco po distanceKm na podstawie
        wynikow analyze_suspect dla wszystkich osob.
        """
        valid = [
            row
            for row in self.analyzed_results.values()
            if row.get("hasLocations") and isinstance(row.get("distanceKm"), (int, float))
        ]
        return sorted(valid, key=lambda x: (-int(x.get("cityHits", 0)), float(x["distanceKm"])))

    def _is_incorrect_identification(self, verify_response: dict[str, Any]) -> bool:
        """
        Sprawdza czy odpowiedz /verify oznacza blad identyfikacji (-910).
        """
        return extract_verify_code(verify_response) == -910

    def _is_verify_success(self, verify_response: dict[str, Any]) -> bool:
        """
        Sprawdza czy odpowiedz /verify wyglada na sukces.
        Poprawny sukces to code == 0.
        """
        if not isinstance(verify_response, dict):
            return False

        body = verify_response.get("json")
        raw_text = str(verify_response.get("raw_text", ""))

        if isinstance(body, dict):
            code = body.get("code")
            return code == 0

        return "FLG:" in raw_text or "{FLG:" in raw_text

    def _verify_next_people_after_910(
        self,
        *,
        submitted_name: str,
        submitted_surname: str,
    ) -> dict[str, Any]:
        """
        Po bledzie -910 probuje kolejnych osob z rankingu (distanceKm rosnaco),
        pobierajac dla nich accessLevel i wysylajac do /verify z ich powerPlant.
        """
        print("[tool] submit_findhim_answer: start fallback next-person retry")
        ranking = self._ranked_candidates_from_analyzed()
        last_response: dict[str, Any] | None = None
        tried: list[dict[str, Any]] = []

        for row in ranking:
            name = str(row["name"]).strip()
            surname = str(row["surname"]).strip()
            birth_year = int(row["birthYear"])
            candidate_codes: list[str] = []
            for candidate in row.get("plantCandidates", []):
                code = str(candidate.get("code", "")).strip()
                if code and code not in candidate_codes:
                    candidate_codes.append(code)
            if not candidate_codes:
                candidate_codes = [str(row["powerPlant"]).strip()]

            if name.lower() == submitted_name.lower() and surname.lower() == submitted_surname.lower():
                continue

            access_level = fetch_access_level(self.api_key, name, surname, birth_year)
            for plant_code in candidate_codes:
                print(
                    f"[tool] next-person try: name={name} surname={surname} "
                    f"accessLevel={access_level} powerPlant={plant_code}"
                )
                response = submit_verify(
                    api_key=self.api_key,
                    name=name,
                    surname=surname,
                    access_level=access_level,
                    power_plant=plant_code,
                )
                log_verify_attempt(
                    stage="fallback-next-person",
                    name=name,
                    surname=surname,
                    plant=plant_code,
                    verify_response=response,
                )
                last_response = response
                tried.append(
                    {
                        "name": name,
                        "surname": surname,
                        "birthYear": birth_year,
                        "accessLevel": access_level,
                        "powerPlant": plant_code,
                        "verifyCode": response.get("json", {}).get("code")
                        if isinstance(response.get("json"), dict)
                        else None,
                    }
                )
                if self._is_verify_success(response):
                    return {
                        "fallbackUsed": True,
                        "strategy": "next_person_after_-910",
                        "selected": {
                            "name": name,
                            "surname": surname,
                            "birthYear": birth_year,
                            "accessLevel": access_level,
                            "powerPlant": plant_code,
                        },
                        "tried": tried,
                        "verify": response,
                    }

        return {
            "fallbackUsed": True,
            "strategy": "next_person_after_-910",
            "error": "All next-person retries finished without success",
            "tried": tried,
            "lastVerifyResponse": last_response,
        }

    def get_access_level(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Zwraca accessLevel dla jednej osoby.
        """
        level = fetch_access_level(
            api_key=self.api_key,
            name=str(args["name"]).strip(),
            surname=str(args["surname"]).strip(),
            birth_year=int(args["birthYear"]),
        )
        return {"accessLevel": level}

    def submit_findhim_answer(self, args: dict[str, Any]) -> dict[str, Any]:
        """
        Przekazuje finalna odpowiedz do /verify i zwraca wynik walidacji.
        """
        missing_city_estimates = self._missing_city_estimates()
        if missing_city_estimates:
            return {
                "ok": False,
                "error": "Missing estimated coordinates for power-plant cities.",
                "missingCities": missing_city_estimates,
                "hint": "Call estimate_city_coordinates for all missing cities before submit.",
            }

        analyzed = set(self.analyzed_results.keys())
        missing = self.expected_suspects - analyzed
        if missing:
            missing_list = sorted(
                [{"name": m[0], "surname": m[1], "birthYear": m[2]} for m in missing], key=lambda x: x["surname"]
            )
            return {
                "ok": False,
                "error": "Analyze all suspects before submit.",
                "missingSuspects": missing_list,
            }

        best = self._best_candidate_from_analyzed()
        if best is None:
            return {"ok": False, "error": "No valid analyzed candidate with locations."}

        ranking = sorted(
            [
                {
                    "name": row.get("name"),
                    "surname": row.get("surname"),
                    "birthYear": row.get("birthYear"),
                    "distanceKm": row.get("distanceKm"),
                    "powerPlant": row.get("powerPlant"),
                    "cityHits": row.get("cityHits"),
                }
                for row in self.analyzed_results.values()
                if row.get("hasLocations") and isinstance(row.get("distanceKm"), (int, float))
            ],
            key=lambda x: float(x["distanceKm"]),
        )
        print("[tool] submit_findhim_answer: ranking by distanceKm:")
        print(json.dumps(ranking, ensure_ascii=False, indent=2))

        submitted_name = str(args["name"]).strip()
        submitted_surname = str(args["surname"]).strip()
        submitted_plant = str(args["powerPlant"]).strip()
        expected_name = str(best["name"]).strip()
        expected_surname = str(best["surname"]).strip()
        expected_plant = str(best["powerPlant"]).strip()
        if (
            submitted_name.lower() != expected_name.lower()
            or submitted_surname.lower() != expected_surname.lower()
            or submitted_plant != expected_plant
        ):
            return {
                "ok": False,
                "error": "Submitted candidate does not match best analyzed candidate.",
                "expected": {
                    "name": expected_name,
                    "surname": expected_surname,
                    "powerPlant": expected_plant,
                    "distanceKm": best.get("distanceKm"),
                },
            }

        initial_response = submit_verify(
            api_key=self.api_key,
            name=submitted_name,
            surname=submitted_surname,
            access_level=int(args["accessLevel"]),
            power_plant=submitted_plant,
        )
        log_verify_attempt(
            stage="initial",
            name=submitted_name,
            surname=submitted_surname,
            plant=submitted_plant,
            verify_response=initial_response,
        )
        if self._is_incorrect_identification(initial_response):
            print("[tool] submit_findhim_answer: -910, uruchamiam fallback na kolejne osoby")
            return self._verify_next_people_after_910(
                submitted_name=submitted_name,
                submitted_surname=submitted_surname,
            )

        return initial_response

    def dispatch(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        """
        Odpala wskazane narzedzie i zwraca ujednolicony rezultat ok/error.
        """
        try:
            if tool_name == "get_suspects":
                return {"ok": True, "data": self.get_suspects(args)}
            if tool_name == "get_power_plants":
                return {"ok": True, "data": self.get_power_plants(args)}
            if tool_name == "estimate_city_coordinates":
                return {"ok": True, "data": self.estimate_city_coordinates(args)}
            if tool_name == "analyze_suspect":
                return {"ok": True, "data": self.analyze_suspect(args)}
            if tool_name == "get_access_level":
                return {"ok": True, "data": self.get_access_level(args)}
            if tool_name == "submit_findhim_answer":
                return {"ok": True, "data": self.submit_findhim_answer(args)}
            return {"ok": False, "error": f"Unknown tool: {tool_name}"}
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": str(error)}

