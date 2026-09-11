"""Narzędzia do logowania konsolowego i zapisu płaskich artefaktów runa."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class RunPaths:
    """Przechowuje ścieżki outputu dla jednego runa w jednym miejscu."""

    run_dir: Path
    trace_jsonl: Path
    config_json: Path
    request_json: Path
    response_json: Path
    result_json: Path
    summary_txt: Path


def now_iso() -> str:
    """Zwraca znacznik czasu ISO używany w logach i zdarzeniach trace."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Wypisuje krótki, czytelny log runtime w terminalu."""

    print(f"[{now_iso()}] {message}")


def prepare_run_paths(output_dir: Path) -> RunPaths:
    """Tworzy katalog output ze znacznikiem czasu i standardowe ścieżki plików."""

    run_dir = output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        run_dir=run_dir,
        trace_jsonl=run_dir / "run_trace.jsonl",
        config_json=run_dir / "config.json",
        request_json=run_dir / "openrouter_request.json",
        response_json=run_dir / "openrouter_response.json",
        result_json=run_dir / "result.json",
        summary_txt=run_dir / "summary.txt",
    )


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje sformatowany UTF-8 JSON dla reprodukcji i łatwiejszego podglądu."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    """Zapisuje plik tekstowy UTF-8 używany do krótkich podsumowań runa."""

    path.write_text(content, encoding="utf-8")


def append_trace(path: Path, step: str, summary: str, details: dict[str, Any] | None = None) -> None:
    """Dopisuje jedno zdarzenie JSONL trace z krótkim opisem i detalami."""

    event = {
        "ts": now_iso(),
        "step": step,
        "summary": summary,
        "details": details or {},
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
