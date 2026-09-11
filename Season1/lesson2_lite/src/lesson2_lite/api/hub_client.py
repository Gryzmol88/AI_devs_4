import json
from typing import Any

import requests

from ..constants import ANSI_CYAN, ANSI_GREEN, ANSI_RED, ANSI_RESET, ANSI_YELLOW
from .retry import request_json


def fetch_power_plants(api_key: str) -> list[dict[str, Any]]:
    """
    Pobiera liste elektrowni z huba i normalizuje do: code, city, isActive.
    Wspolrzedne miast beda estymowane przez LLM przez dedykowane narzedzie.
    """
    raw = request_json("GET", f"https://hub.ag3nts.org/data/{api_key}/findhim_locations.json")

    items: list[dict[str, Any]] = []
    if isinstance(raw, list):
        items = [i for i in raw if isinstance(i, dict)]
    elif isinstance(raw, dict):
        if isinstance(raw.get("items"), list):
            items = [i for i in raw["items"] if isinstance(i, dict)]
        elif isinstance(raw.get("answer"), list):
            items = [i for i in raw["answer"] if isinstance(i, dict)]
        elif isinstance(raw.get("power_plants"), dict):
            for city, details in raw["power_plants"].items():
                if isinstance(details, dict):
                    merged = {"city": city}
                    merged.update(details)
                    items.append(merged)

    plants: list[dict[str, Any]] = []
    for item in items:
        code = item.get("code") or item.get("powerPlant") or item.get("id")
        city = str(item.get("city", "")).strip()
        is_active = bool(item.get("is_active", True))
        if code is None:
            continue

        plants.append(
            {
                "code": str(code),
                "city": city,
                "isActive": is_active,
            }
        )

    return plants


def fetch_person_locations(api_key: str, name: str, surname: str) -> list[tuple[float, float]]:
    """
    Pobiera lokalizacje osoby z /api/location i zwraca liste krotek (lat, lon).
    """
    raw = request_json(
        "POST",
        "https://hub.ag3nts.org/api/location",
        payload={"apikey": api_key, "name": name, "surname": surname},
    )
    items = raw if isinstance(raw, list) else raw.get("locations", raw.get("result", []))

    output: list[tuple[float, float]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        lat = item.get("lat", item.get("latitude"))
        lon = item.get("lon", item.get("lng", item.get("longitude")))
        if lat is None or lon is None:
            continue
        output.append((float(lat), float(lon)))
    return output


def fetch_access_level(api_key: str, name: str, surname: str, birth_year: int) -> int:
    """
    Pobiera poziom dostepu osoby z endpointu /api/accesslevel.
    """
    raw = request_json(
        "POST",
        "https://hub.ag3nts.org/api/accesslevel",
        payload={
            "apikey": api_key,
            "name": name,
            "surname": surname,
            "birthYear": int(birth_year),
        },
    )
    if isinstance(raw, dict):
        value = raw.get("accessLevel", raw.get("access_level"))
        if isinstance(value, int):
            return value
    raise ValueError(f"Niepoprawna odpowiedz z /api/accesslevel: {raw}")


def submit_verify(api_key: str, name: str, surname: str, access_level: int, power_plant: str) -> dict[str, Any]:
    """
    Wysyla finalna odpowiedz zadania findhim do /verify i zwraca odpowiedz serwera.
    """
    payload = {
        "apikey": api_key,
        "task": "findhim",
        "answer": {
            "name": name,
            "surname": surname,
            "accessLevel": int(access_level),
            "powerPlant": power_plant,
        },
    }
    print(f"{ANSI_CYAN}[VERIFY:request]{ANSI_RESET} {json.dumps(payload, ensure_ascii=False)}")
    response = requests.post("https://hub.ag3nts.org/verify", json=payload, timeout=30)

    raw_text = response.text
    parsed_json: Any | None = None
    try:
        parsed_json = response.json()
    except Exception:  # noqa: BLE001
        parsed_json = None

    return {
        "status_code": response.status_code,
        "ok_http": response.ok,
        "headers": dict(response.headers),
        "raw_text": raw_text,
        "json": parsed_json,
    }


def extract_verify_code(verify_response: dict[str, Any]) -> int | None:
    """
    Wyciaga pole code z odpowiedzi /verify (jesli istnieje).
    """
    body = verify_response.get("json")
    if isinstance(body, dict):
        code = body.get("code")
        if isinstance(code, int):
            return code
    return None


def log_verify_attempt(*, stage: str, name: str, surname: str, plant: str, verify_response: dict[str, Any]) -> None:
    """
    Wypisuje czytelny, kolorowy log proby wysylki do /verify:
    osoba, elektrownia, status HTTP oraz kod bledu code.
    """
    status_code = verify_response.get("status_code")
    code = extract_verify_code(verify_response)
    ok_http = bool(verify_response.get("ok_http"))
    body = verify_response.get("json")
    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, str) or not message.strip():
        message = str(verify_response.get("raw_text", "")).strip()

    color = ANSI_GREEN if ok_http and (code is None or code >= 0) else ANSI_RED
    if code == -910:
        color = ANSI_YELLOW

    print(
        f"{ANSI_CYAN}[VERIFY:{stage}]{ANSI_RESET} "
        f"{color}name={name} surname={surname} powerPlant={plant} "
        f"http={status_code} code={code} message={message}{ANSI_RESET}"
    )

