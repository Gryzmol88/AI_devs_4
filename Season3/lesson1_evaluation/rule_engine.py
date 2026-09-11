"""Deterministyczne wykrywanie anomalii w odczytach sensorów."""

from __future__ import annotations

from typing import Dict, List, Tuple

from models import FIELD_TO_SENSOR_TYPE, RuleAnomaly, SensorRecord


FIELD_RANGES: Dict[str, Tuple[float, float]] = {
    "temperature_K": (553.0, 873.0),
    "pressure_bar": (60.0, 160.0),
    "water_level_meters": (5.0, 15.0),
    "voltage_supply_v": (229.0, 231.0),
    "humidity_percent": (40.0, 80.0),
}


def evaluate_record_rules(record: SensorRecord) -> RuleAnomaly:
    """Weryfikuje pojedynczy rekord względem reguł zadania.

    Args:
        record: Odczyt sensora do walidacji.

    Returns:
        Obiekt RuleAnomaly. Pusta lista reasons oznacza brak anomalii.
    """

    reasons: List[str] = []
    active_types = record.active_sensor_types()

    for field_name, sensor_type in FIELD_TO_SENSOR_TYPE.items():
        value = getattr(record, field_name)
        if sensor_type in active_types:
            min_value, max_value = FIELD_RANGES[field_name]
            if not (min_value <= value <= max_value):
                reasons.append(
                    f"{field_name}={value} poza zakresem [{min_value}, {max_value}] dla aktywnego sensora"
                )
        else:
            if value != 0:
                reasons.append(
                    f"{field_name}={value} powinno być 0 dla nieaktywnego typu sensora {sensor_type}"
                )

    unknown_types = [sensor for sensor in active_types if sensor not in FIELD_TO_SENSOR_TYPE.values()]
    if unknown_types:
        reasons.append(f"Nieznany typ sensora: {', '.join(sorted(unknown_types))}")

    return RuleAnomaly(file_id=record.file_id, reasons=reasons)


def detect_rule_anomalies(records: List[SensorRecord]) -> Dict[str, RuleAnomaly]:
    """Uruchamia deterministyczne kontrole reguł dla wszystkich rekordów.

    Args:
        records: Rekordy sensorów do oceny.

    Returns:
        Mapowanie file_id -> RuleAnomaly tylko dla plików z anomalią.
    """

    anomalies: Dict[str, RuleAnomaly] = {}
    for record in records:
        anomaly = evaluate_record_rules(record)
        if anomaly.reasons:
            anomalies[record.file_id] = anomaly
    return anomalies
