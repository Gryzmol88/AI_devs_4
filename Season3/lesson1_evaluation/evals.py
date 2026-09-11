"""Metryki ewaluacji i schemat raportu dla lekcji 1."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field


class GoldLabel(BaseModel):
    """Pojedynczy wpis etykiety referencyjnej do ewaluacji.

    Attributes:
        file_id: Identyfikator pliku.
        expected_recheck: Czy plik powinien trafić do finalnej listy recheck.
        expected_rule_anomaly: Opcjonalny oczekiwany wynik reguł deterministycznych.
        expected_note_stance: Opcjonalna oczekiwana klasyfikacja notatki.
    """

    file_id: str
    expected_recheck: bool
    expected_rule_anomaly: Optional[bool] = None
    expected_note_stance: Optional[str] = None


class EvalThresholds(BaseModel):
    """Progi używane do wyliczenia PASS/FAIL dla uruchomienia."""

    precision_min: float = 0.995
    recall_min: float = 0.999
    f1_min: float = 0.99
    notes_accuracy_min: float = 0.97
    llm_usage_ratio_max: float = 0.05
    runtime_seconds_max: float = 120.0


class EvalMetrics(BaseModel):
    """Wyliczone wartości metryk dla pojedynczego uruchomienia."""

    rules_precision: float
    rules_recall: float
    recheck_f1: float
    notes_accuracy: float
    llm_usage_ratio: float
    runtime_seconds: float


class EvalReport(BaseModel):
    """Pełny raport ewaluacyjny zapisywany do katalogu output.

    Attributes:
        thresholds: Zestaw progów decyzji pass/fail.
        metrics: Wyliczone wartości metryk.
        pass_all: Czy wszystkie progi zostały spełnione.
        sample_count: Liczba wpisów z gold set użytych do oceny.
        notes: Dodatkowe uwagi dotyczące założeń jakości danych.
    """

    thresholds: EvalThresholds
    metrics: EvalMetrics
    pass_all: bool
    sample_count: int
    notes: List[str] = Field(default_factory=list)


def _safe_div(numerator: float, denominator: float) -> float:
    """Zwraca wynik dzielenia z ochroną przed dzieleniem przez zero."""

    return numerator / denominator if denominator else 0.0


def _precision_recall_f1(predicted: Set[str], expected: Set[str]) -> Dict[str, float]:
    """Liczy precision, recall i F1 dla predykcji zbiorowych.

    Args:
        predicted: Przewidziane identyfikatory plików.
        expected: Oczekiwane identyfikatory plików.

    Returns:
        Słownik z kluczami precision, recall i f1.
    """

    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    return {"precision": precision, "recall": recall, "f1": f1}


def load_gold_labels(path: Path) -> List[GoldLabel]:
    """Wczytuje gold labels z pliku JSON.

    Oczekiwany format pliku:
    {
      "labels": [
        {"file_id": "0001", "expected_recheck": true}
      ]
    }

    Args:
        path: Ścieżka do pliku JSON z etykietami referencyjnymi.

    Returns:
        Sparsowaną listę etykiet referencyjnych.
    """

    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    labels_raw = payload.get("labels", [])
    return [GoldLabel.model_validate(item) for item in labels_raw]


def compute_eval_report(
    gold_labels: List[GoldLabel],
    predicted_recheck: List[str],
    rules_predicted: List[str],
    rules_expected: Optional[List[str]],
    notes_accuracy: float,
    llm_usage_ratio: float,
    runtime_seconds: float,
    thresholds: Optional[EvalThresholds] = None,
) -> EvalReport:
    """Wylicza pełny raport ewaluacyjny dla bieżącego uruchomienia.

    Args:
        gold_labels: Wpisy referencyjne.
        predicted_recheck: Przewidziane finalne identyfikatory recheck.
        rules_predicted: Predykcje anomalii regułowych.
        rules_expected: Opcjonalny oczekiwany zbiór anomalii regułowych.
        notes_accuracy: Trafność klasyfikacji notatek na opisanej próbce.
        llm_usage_ratio: Udział rekordów wysłanych do LLM.
        runtime_seconds: Całkowity czas wykonania pipeline w sekundach.
        thresholds: Opcjonalne nadpisanie progów.

    Returns:
        Obiekt EvalReport.
    """

    active_thresholds = thresholds or EvalThresholds()
    expected_recheck = {label.file_id for label in gold_labels if label.expected_recheck}
    recheck_stats = _precision_recall_f1(set(predicted_recheck), expected_recheck)

    if rules_expected is None:
        rule_precision = recheck_stats["precision"]
        rule_recall = recheck_stats["recall"]
    else:
        rule_stats = _precision_recall_f1(set(rules_predicted), set(rules_expected))
        rule_precision = rule_stats["precision"]
        rule_recall = rule_stats["recall"]

    metrics = EvalMetrics(
        rules_precision=rule_precision,
        rules_recall=rule_recall,
        recheck_f1=recheck_stats["f1"],
        notes_accuracy=notes_accuracy,
        llm_usage_ratio=llm_usage_ratio,
        runtime_seconds=runtime_seconds,
    )

    pass_all = all(
        [
            metrics.rules_precision >= active_thresholds.precision_min,
            metrics.rules_recall >= active_thresholds.recall_min,
            metrics.recheck_f1 >= active_thresholds.f1_min,
            metrics.notes_accuracy >= active_thresholds.notes_accuracy_min,
            metrics.llm_usage_ratio <= active_thresholds.llm_usage_ratio_max,
            metrics.runtime_seconds <= active_thresholds.runtime_seconds_max,
        ]
    )

    notes = [
        "Jeśli rules_expected jest puste, rules precision/recall liczone są jak dla metryki end-to-end.",
        "notes_accuracy powinno być mierzone na ręcznie oznaczonej próbce operator_notes.",
    ]
    return EvalReport(
        thresholds=active_thresholds,
        metrics=metrics,
        pass_all=pass_all,
        sample_count=len(gold_labels),
        notes=notes,
    )
