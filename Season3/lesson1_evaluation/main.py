"""Punkt wejścia do pipeline zadania S03E01 evaluation."""

from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Dict

from aggregator import build_reason_index, detect_note_consistency_anomalies, merge_recheck_ids
from config import Settings
from data_loader import download_zip, extract_zip, load_all_records
from evals import compute_eval_report, load_gold_labels
from io_utils import write_json, write_text
from models import FinalResult
from notes_llm import OpenRouterNotesClassifier
from rule_engine import detect_rule_anomalies
from utils_logging import log_step
from verify_client import submit_verification


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty linii poleceń dla pipeline.

    Returns:
        Sparsowane argumenty uruchomienia.
    """

    parser = argparse.ArgumentParser(description="Lekcja 1: pipeline evaluation")
    parser.add_argument("--download", action="store_true", help="Pobiera archiwum ZIP z sensorami.")
    parser.add_argument("--extract", action="store_true", help="Rozpakowuje ZIP do katalogu sensorów.")
    parser.add_argument("--verify", action="store_true", help="Wysyła finalny payload do endpointu verify.")
    parser.add_argument("--gold-path", type=Path, default=None, help="Ścieżka do gold labels JSON dla eval report.")
    parser.add_argument(
        "--notes-gold-path",
        type=Path,
        default=None,
        help="Ścieżka do JSON z etykietami notatek dla metryki notes accuracy.",
    )
    return parser.parse_args()


def _load_notes_gold(path: Path) -> Dict[str, str]:
    """Wczytuje opcjonalne etykiety referencyjne dla notatek.

    Oczekiwany format:
    {
      "labels": [
        {"note": "...", "expected_stance": "ok|anomaly|uncertain"}
      ]
    }

    Args:
        path: Ścieżka do pliku JSON z etykietami notatek.

    Returns:
        Mapowanie tekst notatki -> oczekiwana etykieta.
    """

    import json

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    labels = payload.get("labels", [])
    output: Dict[str, str] = {}
    for item in labels:
        if not isinstance(item, dict):
            continue
        note = item.get("note")
        stance = item.get("expected_stance")
        if isinstance(note, str) and isinstance(stance, str):
            output[note] = stance
    return output


def _compute_notes_accuracy(notes_gold: Dict[str, str], predicted: Dict[str, str]) -> float:
    """Liczy trafność klasyfikacji notatek na oznaczonej próbce.

    Args:
        notes_gold: Mapowanie oczekiwanych etykiet notatek.
        predicted: Mapowanie przewidzianych etykiet notatek.

    Returns:
        Wartość accuracy z zakresu [0, 1]. Zwraca 1.0 bez etykiet.
    """

    if not notes_gold:
        return 1.0
    total = 0
    correct = 0
    for note, expected in notes_gold.items():
        pred = predicted.get(note)
        if pred is None:
            continue
        total += 1
        if pred == expected:
            correct += 1
    return (correct / total) if total else 0.0


def main() -> None:
    """Uruchamia pełny pipeline detekcji anomalii i zapisuje artefakty."""

    started_at = time.perf_counter()
    args = parse_args()
    settings = Settings()
    settings.ensure_directories()

    log_step("Start programu.")
    log_step(f"Wybrany model: {settings.openrouter_model}")
    log_step(f"Katalog sensorów: {settings.sensors_dir}")
    log_step(f"Katalog output: {settings.output_dir}")

    if args.download:
        log_step("Pobieranie archiwum ZIP z sensorami.")
        download_zip(settings.sensors_zip_url, settings.sensors_zip_path)
        log_step(f"Pobrano archiwum: {settings.sensors_zip_path}")

    if args.extract:
        log_step("Rozpakowywanie archiwum ZIP.")
        extract_zip(settings.sensors_zip_path, settings.sensors_dir)
        log_step("Rozpakowanie zakończone.")

    log_step("Wczytywanie rekordów sensorów.")
    records = load_all_records(settings.sensors_dir)
    log_step(f"Liczba wczytanych rekordów: {len(records)}")

    log_step("Uruchamianie reguł deterministycznych.")
    rule_anomalies = detect_rule_anomalies(records)
    log_step(f"Wykryte anomalie regułowe: {len(rule_anomalies)}")
    write_json(
        settings.output_dir / "step1_rules_anomalies.json",
        {file_id: anomaly.model_dump() for file_id, anomaly in rule_anomalies.items()},
    )

    unique_notes = sorted({record.operator_notes for record in records})
    log_step(f"Liczba unikalnych notatek do oceny: {len(unique_notes)}")
    classifier = OpenRouterNotesClassifier(
        settings=settings,
        cache_path=settings.output_dir / "notes_cache.json",
    )
    note_assessments = classifier.classify_unique_notes(unique_notes)
    write_json(
        settings.output_dir / "step2_notes_assessments.json",
        {note: assessment.model_dump() for note, assessment in note_assessments.items()},
    )

    log_step("Sprawdzanie spójności notatek z danymi.")
    note_anomalies = detect_note_consistency_anomalies(records, rule_anomalies, note_assessments)
    log_step(f"Wykryte anomalie spójności notatek: {len(note_anomalies)}")
    write_json(settings.output_dir / "step2_note_consistency_anomalies.json", note_anomalies)

    recheck = merge_recheck_ids(rule_anomalies, note_anomalies)
    reason_index = build_reason_index(rule_anomalies, note_anomalies)

    log_step(f"Rozmiar finalnej listy recheck: {len(recheck)}")
    write_json(settings.output_dir / "step3_merged_recheck.json", {"recheck": recheck})
    write_json(settings.output_dir / "step3_reason_index.json", reason_index)

    api_key = settings.hub_api_key or ""
    final_payload = FinalResult(apikey=api_key, task=settings.task_name, answer={"recheck": recheck})
    write_json(settings.output_dir / "final_payload.json", final_payload.model_dump())
    write_text(settings.output_dir / "final_result.txt", ",".join(recheck))

    llm_used_notes = sum(1 for assessment in note_assessments.values() if assessment.source == "llm")
    llm_usage_ratio = (llm_used_notes / len(records)) if records else 0.0
    runtime_seconds = time.perf_counter() - started_at

    if args.gold_path and args.gold_path.exists():
        log_step("Wyliczanie raportu ewaluacyjnego na podstawie gold labels.")
        gold_labels = load_gold_labels(args.gold_path)
        notes_gold = _load_notes_gold(args.notes_gold_path) if args.notes_gold_path and args.notes_gold_path.exists() else {}
        notes_predicted = {note: assessment.stance for note, assessment in note_assessments.items()}
        notes_accuracy = _compute_notes_accuracy(notes_gold, notes_predicted)
        report = compute_eval_report(
            gold_labels=gold_labels,
            predicted_recheck=recheck,
            rules_predicted=list(rule_anomalies.keys()),
            rules_expected=None,
            notes_accuracy=notes_accuracy,
            llm_usage_ratio=llm_usage_ratio,
            runtime_seconds=runtime_seconds,
        )
        write_json(settings.output_dir / "eval_report.json", report.model_dump())
        summary_lines = [
            f"PASS: {report.pass_all}",
            f"rules_precision={report.metrics.rules_precision:.4f}",
            f"rules_recall={report.metrics.rules_recall:.4f}",
            f"recheck_f1={report.metrics.recheck_f1:.4f}",
            f"notes_accuracy={report.metrics.notes_accuracy:.4f}",
            f"llm_usage_ratio={report.metrics.llm_usage_ratio:.4f}",
            f"runtime_seconds={report.metrics.runtime_seconds:.2f}",
        ]
        write_text(settings.output_dir / "eval_summary.txt", "\n".join(summary_lines))
        log_step(f"Wynik ewaluacji PASS: {report.pass_all}")
    else:
        log_step("Brak gold labels; pomijam eval report.")

    if args.verify:
        if not settings.verify_url:
            log_step("Brak VERIFY_URL, pomijam weryfikację.")
        elif not final_payload.apikey:
            log_step("Brak HUB_API_KEY, pomijam weryfikację.")
        else:
            log_step("Wysyłanie payloadu do endpointu weryfikacji.")
            response = submit_verification(final_payload, settings.verify_url)
            write_json(settings.output_dir / "verify_response.json", response)
            log_step("Zapisano odpowiedź weryfikacji do output/verify_response.json")

    log_step("Pipeline zakończony.")


if __name__ == "__main__":
    main()
