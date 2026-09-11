"""Łączenie anomalii deterministycznych i notatek do finalnej listy recheck."""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from models import NoteAssessment, RuleAnomaly, SensorRecord


def detect_note_consistency_anomalies(
    records: List[SensorRecord],
    rule_anomalies: Dict[str, RuleAnomaly],
    note_assessments: Dict[str, NoteAssessment],
) -> Dict[str, List[str]]:
    """Wykrywa niespójności między notatką operatora a danymi pomiarowymi.

    Args:
        records: Wszystkie rekordy do oceny.
        rule_anomalies: Anomalie regułowe zindeksowane po file_id.
        note_assessments: Oceny notatek zindeksowane po pełnym tekście notatki.

    Returns:
        Mapowanie file_id -> lista powodów niespójności.
    """

    note_anomalies: Dict[str, List[str]] = {}

    for record in records:
        has_rule_anomaly = record.file_id in rule_anomalies
        assessment = note_assessments.get(record.operator_notes)
        if assessment is None:
            continue

        reasons: List[str] = []
        if assessment.stance == "ok" and has_rule_anomaly:
            reasons.append("Notatka operatora mówi OK, ale dane zawierają anomalie.")
        elif assessment.stance == "anomaly" and not has_rule_anomaly:
            reasons.append("Notatka operatora zgłasza błąd, ale dane mieszczą się w normie.")

        if reasons:
            note_anomalies[record.file_id] = reasons

    return note_anomalies


def merge_recheck_ids(
    rule_anomalies: Dict[str, RuleAnomaly], note_anomalies: Dict[str, List[str]]
) -> List[str]:
    """Łączy wszystkie źródła anomalii do posortowanej listy unikalnych ID.

    Args:
        rule_anomalies: Anomalie wykryte regułami.
        note_anomalies: Anomalie wynikające z niespójności notatek.

    Returns:
        Posortowaną listę unikalnych identyfikatorów plików.
    """

    merged: Set[str] = set(rule_anomalies.keys()) | set(note_anomalies.keys())
    return sorted(merged)


def build_reason_index(
    rule_anomalies: Dict[str, RuleAnomaly], note_anomalies: Dict[str, List[str]]
) -> Dict[str, Dict[str, List[str]]]:
    """Buduje indeks szczegółów per plik używany w snapshotach output.

    Args:
        rule_anomalies: Anomalie wykryte regułami.
        note_anomalies: Anomalie wynikające z niespójności notatek.

    Returns:
        Mapowanie file_id -> ustrukturyzowane powody z każdego źródła.
    """

    file_ids = sorted(set(rule_anomalies.keys()) | set(note_anomalies.keys()))
    result: Dict[str, Dict[str, List[str]]] = {}
    for file_id in file_ids:
        result[file_id] = {
            "rule_reasons": rule_anomalies.get(file_id, RuleAnomaly(file_id=file_id, reasons=[])).reasons,
            "note_reasons": note_anomalies.get(file_id, []),
        }
    return result
