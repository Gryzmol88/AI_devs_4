"""Skanery tropów w danych wejściowych i artefaktach misji głównej."""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

from http_utils import JsonHttpClient
from models import find_flag_in_payload


def scan_main_output(main_output_dir: Path) -> dict[str, Any]:
    """Przeszukuje `output` misji głównej pod kątem tropów i flag.

    Args:
        main_output_dir: Ścieżka do katalogu output misji głównej.

    Returns:
        Raport skanowania jako słownik.
    """

    report: dict[str, Any] = {
        "scanned_dir": str(main_output_dir),
        "files_scanned": 0,
        "flags_found": [],
        "censorship_hits": [],
    }
    if not main_output_dir.exists():
        report["error"] = "Brak katalogu output misji głównej."
        return report

    keyword_pattern = re.compile(r"cenzur|censor|redact|mask|ocenzur", re.IGNORECASE)
    for path in sorted(main_output_dir.rglob("*.json")):
        report["files_scanned"] += 1
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        found_flag = find_flag_in_payload(payload)
        if found_flag:
            report["flags_found"].append({"file": str(path), "flag": found_flag})

        joined_values = "\n".join(str(value) for value in _walk_values(payload))
        if keyword_pattern.search(joined_values):
            report["censorship_hits"].append(str(path))

    return report


def scan_input_data(base_url: str, client: JsonHttpClient) -> dict[str, Any]:
    """Skanuje dane wejściowe CSV pod tropy związane z cenzurą i flagą.

    Args:
        base_url: Bazowy URL katalogu danych wejściowych.
        client: Klient HTTP do pobierania danych.

    Returns:
        Raport skanowania danych wejściowych.
    """

    report: dict[str, Any] = {
        "base_url": base_url,
        "files": {},
        "suspicious_item_codes": [],
        "suspicious_rows": [],
    }

    index_html = client.get_text(base_url)
    csv_files = sorted(set(re.findall(r'href=["\']([^"\']+\.csv)["\']', index_html, flags=re.IGNORECASE)))
    for filename in csv_files:
        csv_url = urljoin(base_url, filename)
        content = client.get_text(csv_url)
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        joined = "\n".join(",".join(row) for row in rows)
        report["files"][filename] = {
            "rows_count": max(0, len(rows) - 1),
            "has_flg_pattern": bool(re.search(r"\{FLG:[^}]+\}", joined)),
            "has_censorship_pattern": bool(re.search(r"cenzur|censor|redact|mask|\*{2,}", joined, re.IGNORECASE)),
        }

        for index, row in enumerate(rows[1:], start=2):
            for cell in row:
                if re.search(r"FLG", cell, re.IGNORECASE):
                    report["suspicious_rows"].append(
                        {"file": filename, "line": index, "row": row}
                    )
                    if filename.lower() == "items.csv" and len(row) >= 2:
                        report["suspicious_item_codes"].append(row[1])

    return report


def _walk_values(payload: Any) -> list[Any]:
    """Spłaszcza wszystkie wartości atomowe z JSON-a.

    Args:
        payload: Struktura wejściowa.

    Returns:
        Lista wartości atomowych.
    """

    values: list[Any] = []
    if isinstance(payload, dict):
        for value in payload.values():
            values.extend(_walk_values(value))
    elif isinstance(payload, list):
        for item in payload:
            values.extend(_walk_values(item))
    else:
        values.append(payload)
    return values

