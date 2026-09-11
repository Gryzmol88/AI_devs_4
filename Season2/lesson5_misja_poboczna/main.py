"""Eksperyment sidequest: wysłanie drona na współrzędne geograficzne Radomia.

Skrypt:
1. Pobiera współrzędne Radomia z publicznego geokodera.
2. Wstawia je do instrukcji drona jako `set(x,y)`.
3. Wysyła instrukcje do `/verify` dla tasku `drone`.
4. Zapisuje pełny ślad do `output/<timestamp>/`.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Konfiguracja runtime ładowana z environmentu i pliku `.env`."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    hub_api_key: SecretStr
    verify_url: str = "https://hub.ag3nts.org/verify"
    task_name: str = "drone"
    request_timeout_seconds: int = Field(default=60, ge=10, le=300)


class GeocodeResult(BaseModel):
    """Wynik geokodowania miasta Radom."""

    lat: float
    lon: float
    display_name: str


def now_iso() -> str:
    """Zwraca znacznik czasu ISO używany w logach i trace."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Wypisuje krótki log do terminala."""

    print(f"[{now_iso()}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje UTF-8 JSON w czytelnej formie."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_trace(path: Path, step: str, summary: str, details: dict[str, Any] | None = None) -> None:
    """Dopisuje jedno zdarzenie JSONL do trace runa."""

    event = {"ts": now_iso(), "step": step, "summary": summary, "details": details or {}}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_settings(lesson_dir: Path) -> AppSettings:
    """Wczytuje ustawienia z `Season2/.env`."""

    env_path = lesson_dir.parent / ".env"
    return AppSettings(_env_file=env_path, _env_file_encoding="utf-8")


def geocode_radom(timeout_seconds: int) -> GeocodeResult:
    """Pobiera współrzędne Radomia z Nominatim (OpenStreetMap)."""

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": "Radom, Poland",
        "format": "jsonv2",
        "limit": 1,
    }
    headers = {
        "User-Agent": "AI-Devs-Lesson5-Sidequest/1.0",
    }

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(url, params=params, headers=headers)
    response.raise_for_status()
    items = response.json()
    if not items:
        raise RuntimeError("Geokoder nie zwrócił wyników dla Radomia.")

    item = items[0]
    return GeocodeResult(
        lat=float(item["lat"]),
        lon=float(item["lon"]),
        display_name=str(item.get("display_name", "Radom")),
    )


def build_drone_instructions(lat: float, lon: float) -> list[str]:
    """Buduje instrukcje drona z podstawowym profilem lotu i celem geograficznym."""

    return [
        "set(engineON)",
        "set(100%)",
        "setDestinationObject(PWR6132PL)",
        f"set({lat:.6f},{lon:.6f})",
        "set(destroy)",
        "set(return)",
        "set(100m)",
        "flyToLocation",
    ]


def call_verify(settings: AppSettings, instructions: list[str]) -> tuple[dict[str, Any], int]:
    """Wysyła instrukcje drona na endpoint `/verify` i zwraca odpowiedź."""

    payload = {
        "apikey": settings.hub_api_key.get_secret_value(),
        "task": settings.task_name,
        "answer": {"instructions": instructions},
    }
    with httpx.Client(timeout=settings.request_timeout_seconds) as client:
        response = client.post(settings.verify_url, json=payload)
    return response.json(), response.status_code


def main() -> None:
    """Uruchamia eksperyment sidequest i zapisuje wszystkie artefakty runa."""

    lesson_dir = Path(__file__).resolve().parent
    output_dir = lesson_dir / "output" / datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_path = output_dir / "run_trace.jsonl"

    settings = load_settings(lesson_dir)
    write_json(
        output_dir / "config.json",
        {
            "verify_url": settings.verify_url,
            "task_name": settings.task_name,
            "request_timeout_seconds": settings.request_timeout_seconds,
        },
    )

    log("Pobieram współrzędne Radomia")
    geocode = geocode_radom(settings.request_timeout_seconds)
    write_json(output_dir / "geocode_radom.json", geocode.model_dump())
    append_trace(
        trace_path,
        "geocode",
        "Pobrano współrzędne Radomia",
        {"lat": geocode.lat, "lon": geocode.lon, "display_name": geocode.display_name},
    )
    log(f"Radom: lat={geocode.lat:.6f}, lon={geocode.lon:.6f}")

    instructions = build_drone_instructions(geocode.lat, geocode.lon)
    write_json(output_dir / "instructions.json", {"instructions": instructions})
    append_trace(
        trace_path,
        "instructions",
        "Zbudowano instrukcje drona",
        {"count": len(instructions)},
    )

    log("Wysyłam instrukcje do /verify")
    verify_response, status_code = call_verify(settings, instructions)
    write_json(output_dir / "verify_response.json", verify_response)
    append_trace(
        trace_path,
        "verify",
        "Odebrano odpowiedź /verify",
        {"status_code": status_code, "message": verify_response.get("message", "")},
    )
    log(f"/verify HTTP {status_code}: {verify_response.get('message', '')}")

    summary = {
        "status_code": status_code,
        "verify_response": verify_response,
        "coordinates_used": {"lat": geocode.lat, "lon": geocode.lon},
        "instructions_count": len(instructions),
        "output_dir": str(output_dir),
    }
    write_json(output_dir / "result.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

