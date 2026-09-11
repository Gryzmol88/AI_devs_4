"""Sidequest: pojedynczy lot do Radomia na sektor 3x1.

Skrypt celowo wykonuje TYLKO jeden lot:
- destination: PWR8406PL (Radom)
- sektor: 3x1
- LED: fuksja (#FF00FF)
- media: video + image
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


FLAG_RE = re.compile(r"\{FLG:[^}]+\}")


class AppSettings(BaseSettings):
    """Runtime config loaded from environment and Season2/.env."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    hub_api_key: SecretStr
    verify_url: str = "https://hub.ag3nts.org/verify"
    task_name: str = "drone"
    timeout_seconds: int = Field(default=60, ge=10, le=300)

    destination_code: str = "PWR8406PL"
    led_color: str = "#FF00FF"
    grid_cols: int = Field(default=3, ge=1, le=20)
    grid_rows: int = Field(default=4, ge=1, le=20)
    altitude_m: int = Field(default=100, ge=1, le=100)
    power_percent: int = Field(default=100, ge=1, le=100)
    include_media_goals: bool = True
    stop_on_flag: bool = True

    target_col: int = Field(default=3, ge=1, le=20)
    target_row: int = Field(default=1, ge=1, le=20)


class SectorAttempt(BaseModel):
    """One /verify attempt for a single sector."""

    col: int
    row: int
    status_code: int
    instructions: list[str]
    verify_response: dict[str, Any]
    detected_flag: str | None = None


def now_iso() -> str:
    """Return ISO timestamp for logs."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Print concise runtime log line."""

    print(f"[{now_iso()}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Write pretty UTF-8 JSON."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Append one JSONL line."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_settings(lesson_dir: Path) -> AppSettings:
    """Load settings from Season2/.env."""

    env_path = lesson_dir.parent / ".env"
    return AppSettings(_env_file=env_path, _env_file_encoding="utf-8")


def build_instructions(cfg: AppSettings, col: int, row: int) -> list[str]:
    """Build drone instructions for selected sector."""

    instructions: list[str] = [
        "hardReset",
        "set(engineON)",
        f"set({cfg.power_percent}%)",
        f"setDestinationObject({cfg.destination_code})",
        f"setLed({cfg.led_color})",
    ]

    if cfg.include_media_goals:
        instructions.extend(["set(video)", "set(image)"])

    instructions.extend(
        [
            "set(return)",
            f"set({cfg.altitude_m}m)",
            f"set({col},{row})",
            "flyToLocation",
        ]
    )
    return instructions


def post_verify(cfg: AppSettings, instructions: list[str]) -> tuple[dict[str, Any], int]:
    """POST instructions to /verify."""

    payload = {
        "apikey": cfg.hub_api_key.get_secret_value(),
        "task": cfg.task_name,
        "answer": {"instructions": instructions},
    }
    with httpx.Client(timeout=cfg.timeout_seconds) as client:
        response = client.post(cfg.verify_url, json=payload)
    return response.json(), response.status_code


def detect_flag(body: dict[str, Any]) -> str | None:
    """Extract {FLG:...} token from verify response."""

    text = json.dumps(body, ensure_ascii=False)
    match = FLAG_RE.search(text)
    return match.group(0) if match else None


def main() -> None:
    """Run sidequest scan and save full output artifacts."""

    lesson_dir = Path(__file__).resolve().parent
    cfg = load_settings(lesson_dir=lesson_dir)

    run_dir = lesson_dir / "output" / f"radom_sidequest_scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "scan_trace.jsonl"

    write_json(
        run_dir / "config.json",
        {
            "verify_url": cfg.verify_url,
            "task_name": cfg.task_name,
            "destination_code": cfg.destination_code,
            "led_color": cfg.led_color,
            "grid_cols": cfg.grid_cols,
            "grid_rows": cfg.grid_rows,
            "altitude_m": cfg.altitude_m,
            "power_percent": cfg.power_percent,
            "include_media_goals": cfg.include_media_goals,
            "stop_on_flag": cfg.stop_on_flag,
            "target_col": cfg.target_col,
            "target_row": cfg.target_row,
        },
    )

    sectors = [(cfg.target_col, cfg.target_row)]

    log(
        "Start: "
        f"destination={cfg.destination_code}, led={cfg.led_color}, "
        f"sectors={len(sectors)}"
    )

    attempts: list[SectorAttempt] = []
    found_flag: str | None = None

    for col, row in sectors:
        instructions = build_instructions(cfg=cfg, col=col, row=row)
        log(f"Sektor ({col},{row}) -> wysylam {len(instructions)} instrukcji")

        verify_body, status_code = post_verify(cfg=cfg, instructions=instructions)
        flag = detect_flag(verify_body)

        attempt = SectorAttempt(
            col=col,
            row=row,
            status_code=status_code,
            instructions=instructions,
            verify_response=verify_body,
            detected_flag=flag,
        )
        attempts.append(attempt)

        write_json(run_dir / f"sector_{col}_{row}.json", attempt.model_dump())
        append_jsonl(
            trace_path,
            {
                "ts": now_iso(),
                "col": col,
                "row": row,
                "status_code": status_code,
                "message": verify_body.get("message", ""),
                "flag": flag,
            },
        )
        log(f"Sektor ({col},{row}) -> HTTP {status_code}")

        if flag:
            found_flag = flag
            log(f"Flaga: {flag}")
            if cfg.stop_on_flag:
                break

    result = {
        "ok": found_flag is not None,
        "flag": found_flag,
        "attempts_total": len(attempts),
        "output_dir": str(run_dir),
        "attempts": [item.model_dump() for item in attempts],
    }
    write_json(run_dir / "result.json", result)
    log(f"Koniec. Output: {run_dir}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
