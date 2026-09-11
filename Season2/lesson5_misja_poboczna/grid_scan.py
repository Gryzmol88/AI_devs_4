"""Skanowanie siatki 3x4 dronem z celami: zdjęcie + film.

Skrypt wysyła drona do każdego sektora mapy (kolumny 1..3, wiersze 1..4),
zapisuje odpowiedzi `/verify` i kończy się podsumowaniem.
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
    """Konfiguracja runtime ładowana z `.env`."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    hub_api_key: SecretStr
    verify_url: str = "https://hub.ag3nts.org/verify"
    task_name: str = "drone"
    timeout_seconds: int = Field(default=60, ge=10, le=300)

    grid_cols: int = Field(default=3, ge=1, le=20)
    grid_rows: int = Field(default=4, ge=1, le=20)
    altitude_m: int = Field(default=100, ge=1, le=100)
    engine_power_percent: int = Field(default=100, ge=1, le=100)
    destination_code: str = "PWR6132PL"


class SectorResult(BaseModel):
    """Wynik jednej próby dla konkretnego sektora."""

    col: int
    row: int
    status_code: int
    verify_response: dict[str, Any]
    instructions: list[str]


def now_iso() -> str:
    """Zwraca znacznik czasu ISO do logów."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Wypisuje krótki log postępu."""

    print(f"[{now_iso()}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje obiekt jako czytelny UTF-8 JSON."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Dopisuje jeden rekord JSONL."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_settings(lesson_dir: Path) -> AppSettings:
    """Wczytuje ustawienia z `Season2/.env`."""

    env_path = lesson_dir.parent / ".env"
    return AppSettings(_env_file=env_path, _env_file_encoding="utf-8")


def build_instructions(col: int, row: int, cfg: AppSettings) -> list[str]:
    """Buduje instrukcje lotu dla pojedynczego sektora.

    Instrukcje obejmują:
    - uruchomienie silników i mocy,
    - ustawienie celu formalnego,
    - ustawienie celu misji: video + image + return,
    - ustawienie wysokości i sektora,
    - start lotu.
    """

    return [
        "hardReset",
        "set(engineON)",
        f"set({cfg.engine_power_percent}%)",
        f"setDestinationObject({cfg.destination_code})",
        "set(video)",
        "set(image)",
        "set(return)",
        f"set({cfg.altitude_m}m)",
        f"set({col},{row})",
        "flyToLocation",
    ]


def post_verify(cfg: AppSettings, instructions: list[str]) -> tuple[dict[str, Any], int]:
    """Wysyła instrukcje na `/verify` i zwraca odpowiedź JSON + status HTTP."""

    payload = {
        "apikey": cfg.hub_api_key.get_secret_value(),
        "task": cfg.task_name,
        "answer": {"instructions": instructions},
    }
    with httpx.Client(timeout=cfg.timeout_seconds) as client:
        response = client.post(cfg.verify_url, json=payload)
    return response.json(), response.status_code


def main() -> None:
    """Uruchamia pełne skanowanie siatki 3x4 i zapisuje artefakty do output."""

    lesson_dir = Path(__file__).resolve().parent
    cfg = load_settings(lesson_dir=lesson_dir)

    run_dir = lesson_dir / "output" / f"grid_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "scan_trace.jsonl"

    write_json(
        run_dir / "config.json",
        {
            "verify_url": cfg.verify_url,
            "task_name": cfg.task_name,
            "grid_cols": cfg.grid_cols,
            "grid_rows": cfg.grid_rows,
            "altitude_m": cfg.altitude_m,
            "engine_power_percent": cfg.engine_power_percent,
            "destination_code": cfg.destination_code,
        },
    )

    log(f"Start skanowania siatki {cfg.grid_cols}x{cfg.grid_rows}")
    all_results: list[SectorResult] = []

    for row in range(1, cfg.grid_rows + 1):
        for col in range(1, cfg.grid_cols + 1):
            instructions = build_instructions(col=col, row=row, cfg=cfg)
            log(f"Sektor ({col},{row}) -> wysyłam do /verify")
            verify_body, status_code = post_verify(cfg=cfg, instructions=instructions)

            result = SectorResult(
                col=col,
                row=row,
                status_code=status_code,
                verify_response=verify_body,
                instructions=instructions,
            )
            all_results.append(result)

            sector_file = run_dir / f"sector_{col}_{row}.json"
            write_json(sector_file, result.model_dump())
            append_jsonl(
                trace_path,
                {
                    "ts": now_iso(),
                    "col": col,
                    "row": row,
                    "status_code": status_code,
                    "message": verify_body.get("message", ""),
                },
            )
            log(f"Sektor ({col},{row}) -> HTTP {status_code}")

    summary = {
        "ok": True,
        "scanned_sectors": len(all_results),
        "output_dir": str(run_dir),
        "results": [item.model_dump() for item in all_results],
    }
    write_json(run_dir / "result.json", summary)
    log(f"Koniec skanowania, zapisano wyniki: {run_dir}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

