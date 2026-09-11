"""Punkt wejścia eksploratora misji pobocznej dla lesson4."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import get_settings
from http_utils import JsonHttpClient
from io_utils import create_session_output_dir, ensure_output_dir, log_terminal, write_json, write_text
from models import AttemptResult
from payloads import build_payload_candidates
from scanners import scan_input_data, scan_main_output
from verify_explorer import VerifyExplorer


def main() -> None:
    """Uruchamia analizę tropów i opcjonalną eksplorację payloadów `/verify`.

    Efekty uboczne:
        Odczytuje konfigurację z `.env`, wykonuje żądania HTTP i zapisuje
        pełne artefakty sesji do katalogu `output`.
    """

    settings = get_settings()
    base_dir = Path(__file__).resolve().parent
    output_dir = ensure_output_dir(base_dir, settings.output_dir_name)
    session_dir = create_session_output_dir(output_dir)
    client = JsonHttpClient(timeout_seconds=settings.request_timeout_seconds)

    log_terminal("Start misji pobocznej lesson4.")
    log_terminal(f"Sesja output: {session_dir}")

    # 1) Skan artefaktów misji głównej.
    main_output = base_dir.parent / "lesson4_negotiations" / "output"
    main_scan_report = scan_main_output(main_output)
    write_json(session_dir / "step1_main_output_scan.json", main_scan_report)
    log_terminal(
        f"Skan output glownej: files={main_scan_report.get('files_scanned')} "
        f"flags={len(main_scan_report.get('flags_found', []))} "
        f"censorship_hits={len(main_scan_report.get('censorship_hits', []))}"
    )

    # 2) Skan danych wejściowych.
    input_scan_report = scan_input_data(settings.input_base_url, client)
    write_json(session_dir / "step2_input_data_scan.json", input_scan_report)
    log_terminal(
        f"Skan danych wejsciowych: files={len(input_scan_report.get('files', {}))} "
        f"suspicious_rows={len(input_scan_report.get('suspicious_rows', []))}"
    )

    # 3) Budowanie payloadów eksploracyjnych.
    candidates = build_payload_candidates(settings, base_dir=base_dir)
    write_json(
        session_dir / "step3_payload_candidates.json",
        [{"label": label, "payload": payload} for label, payload in candidates],
    )
    log_terminal(f"Przygotowano payloady: {len(candidates)}")

    attempts: list[AttemptResult] = []
    if settings.enable_verify_exploration:
        log_terminal("Start eksploracji /verify.")
        explorer = VerifyExplorer(settings=settings, client=client)
        attempts = explorer.run(candidates)
        for attempt in attempts:
            write_json(
                session_dir / f"step4_attempt_{attempt.attempt_index:03d}_{attempt.label}.json",
                {
                    "attempt_index": attempt.attempt_index,
                    "label": attempt.label,
                    "payload": attempt.payload,
                    "response": attempt.response,
                    "found_flag": attempt.found_flag,
                    "notes": attempt.notes,
                },
            )
        log_terminal(f"Wykonano prob: {len(attempts)}")
    else:
        log_terminal("Eksploracja /verify wylaczona przez konfiguracje.")

    found_flag = _find_side_flag(attempts)
    all_flags = [attempt.found_flag for attempt in attempts if attempt.found_flag]
    final_summary: dict[str, Any] = {
        "found_flag": found_flag,
        "all_flags": all_flags,
        "attempts_count": len(attempts),
        "enable_verify_exploration": settings.enable_verify_exploration,
        "main_output_scan": {
            "flags_found_count": len(main_scan_report.get("flags_found", [])),
            "censorship_hits_count": len(main_scan_report.get("censorship_hits", [])),
        },
        "input_data_scan": {
            "files_count": len(input_scan_report.get("files", {})),
            "suspicious_rows_count": len(input_scan_report.get("suspicious_rows", [])),
            "suspicious_item_codes": input_scan_report.get("suspicious_item_codes", []),
        },
    }
    write_json(session_dir / "final_result.json", final_summary)
    write_text(
        session_dir / "final_result.txt",
        (
            f"found_flag={found_flag or '-'}\n"
            f"attempts_count={len(attempts)}\n"
            f"main_output_flags={len(main_scan_report.get('flags_found', []))}\n"
            f"main_output_censorship_hits={len(main_scan_report.get('censorship_hits', []))}\n"
            f"input_suspicious_rows={len(input_scan_report.get('suspicious_rows', []))}\n"
        ),
    )

    if found_flag:
        log_terminal(f"Znaleziono flage: {found_flag}")
        print(found_flag)
    else:
        log_terminal("Brak flagi w tej sesji.")
        log_terminal("Sprawdz final_result.json i step4_attempt_*.json.")


def _find_side_flag(attempts: list[AttemptResult]) -> str | None:
    """Zwraca pierwszą znalezioną flagę różną od głównej.

    Args:
        attempts: Lista rezultatów prób.

    Returns:
        Pierwsza flaga poboczna albo `None`.
    """

    for attempt in attempts:
        if attempt.found_flag and attempt.found_flag.strip().upper() != "{FLG:WINDFARM}":
            return attempt.found_flag
    return None


if __name__ == "__main__":
    main()
