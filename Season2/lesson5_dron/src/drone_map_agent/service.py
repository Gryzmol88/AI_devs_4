"""Serwis pierwszego agenta: analiza mapy i zwrot koordynatów sektora."""

from __future__ import annotations

import json
from pathlib import Path

from .config import build_runtime_config, load_settings
from .io_utils import append_trace, log, prepare_run_paths, write_json, write_text
from .openrouter_client import OpenRouterVisionClient
from .schemas import CoordinateResult


def run_map_analysis(
    output_root: Path | None = None,
    print_result: bool = True,
) -> tuple[CoordinateResult, Path]:
    """Uruchamia agenta vision i zwraca wynik wraz z katalogiem runa.

    Parametry:
    - `output_root`: opcjonalny katalog bazowy output dla tego etapu.
    - `print_result`: czy wypisać końcowy JSON na stdout.

    Zwraca:
    - `CoordinateResult`: zwalidowany wynik analizy mapy.
    - `Path`: katalog runa zawierający artefakty tego etapu.
    """

    lesson_dir = Path(__file__).resolve().parents[2]
    settings = load_settings(lesson_dir=lesson_dir)
    runtime_cfg = build_runtime_config(settings=settings, lesson_dir=lesson_dir)

    output_dir = output_root or runtime_cfg.output_dir
    paths = prepare_run_paths(output_dir)
    write_json(paths.config_json, runtime_cfg.model_dump(mode="json"))
    append_trace(paths.trace_jsonl, "init", "Zainicjalizowano runtime", {"run_dir": str(paths.run_dir)})
    log(f"Start agenta mapy: {paths.run_dir}")

    client = OpenRouterVisionClient(settings=settings, runtime_cfg=runtime_cfg)
    payload = client.build_payload()
    write_json(paths.request_json, payload)
    append_trace(
        paths.trace_jsonl,
        "build_request",
        "Przygotowano payload do OpenRouter",
        {"model": runtime_cfg.vision_model, "map_url": runtime_cfg.map_url},
    )
    log(f"Wysyłam zapytanie vision (model={runtime_cfg.vision_model})")

    response_json, status_code = client.call(payload=payload)
    write_json(paths.response_json, response_json)
    append_trace(
        paths.trace_jsonl,
        "openrouter_response",
        "Odebrano odpowiedź OpenRouter",
        {"status_code": status_code, "choices": len(response_json.get('choices', []))},
    )
    log(f"Odebrano odpowiedź vision: HTTP {status_code}")

    response_text = client.extract_text(response_json=response_json)
    append_trace(
        paths.trace_jsonl,
        "extract_text",
        "Wyodrębniono tekst asystenta",
        {"text_length": len(response_text)},
    )

    result = client.parse_coordinate_result(text=response_text)
    write_json(paths.result_json, result.model_dump())
    append_trace(
        paths.trace_jsonl,
        "validate_result",
        "Zwalidowano wynik koordynatów",
        {"col": result.col, "row": result.row, "confidence": result.confidence},
    )
    summary = (
        f"Wynik analizy mapy\n"
        f"- kolumna: {result.col}\n"
        f"- wiersz: {result.row}\n"
        f"- siatka: {result.grid_cols}x{result.grid_rows}\n"
        f"- pewność: {result.confidence}\n"
        f"- uzasadnienie: {result.reasoning_short}\n"
    )
    write_text(paths.summary_txt, summary)
    log(f"Analiza mapy zakończona: sektor=({result.col},{result.row})")
    if print_result:
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

    return result, paths.run_dir
