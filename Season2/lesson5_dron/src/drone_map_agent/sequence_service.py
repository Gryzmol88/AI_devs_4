"""Orkiestrator sekwencji: agent mapy -> agent pilota drona."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import build_runtime_config, load_settings
from .io_utils import log, write_json, write_text
from .pilot_service import run_pilot_agent
from .service import run_map_analysis


def run_full_sequence() -> dict:
    """Uruchamia pełną sekwencję dwóch agentów i zapisuje wynik zbiorczy.

    Kolejność:
    1. Agent mapy wyznacza sektor tamy.
    2. Agent pilota buduje instrukcje, wysyła je do `/verify` i iteruje po feedbacku.
    """

    lesson_dir = Path(__file__).resolve().parents[2]
    settings = load_settings(lesson_dir=lesson_dir)
    runtime_cfg = build_runtime_config(settings=settings, lesson_dir=lesson_dir)

    sequence_root = runtime_cfg.output_dir / f"sequence_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    sequence_root.mkdir(parents=True, exist_ok=True)
    log(f"Start sekwencji: {sequence_root}")

    coords, map_run_dir = run_map_analysis(output_root=sequence_root / "01_map", print_result=False)
    log(f"Etap 1 zakończony, koordynaty: ({coords.col},{coords.row})")

    pilot_result, pilot_run_dir = run_pilot_agent(coords=coords, output_root=sequence_root / "02_pilot")
    log("Etap 2 zakończony")

    final_result = {
        "ok": bool(pilot_result.get("ok")),
        "flag": pilot_result.get("flag"),
        "sequence_root": str(sequence_root),
        "map_agent_run_dir": str(map_run_dir),
        "pilot_agent_run_dir": str(pilot_run_dir),
        "coordinates": coords.model_dump(),
    }
    write_json(sequence_root / "sequence_result.json", final_result)
    write_text(
        sequence_root / "sequence_summary.txt",
        (
            f"Sekwencja lesson5_dron\n"
            f"- status: {'OK' if final_result['ok'] else 'NIEUKOŃCZONE'}\n"
            f"- flaga: {final_result['flag']}\n"
            f"- koordynaty: ({coords.col},{coords.row})\n"
            f"- map_agent_run_dir: {map_run_dir}\n"
            f"- pilot_agent_run_dir: {pilot_run_dir}\n"
        ),
    )
    return final_result

