"""Przetwarzanie załączników binarnych (Base64) odbieranych z nasłuchu."""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from pipeline.transcription_processor import _extract_warehouses_count


def decode_attachment_base64(encoded_payload: str) -> bytes:
    """Dekoduje treść załącznika z Base64 do bajtów.

    Args:
        encoded_payload: Dane zakodowane jako Base64.

    Returns:
        Zdekodowane bajty.
    """
    return base64.b64decode(encoded_payload, validate=False)


def parse_attachment_content(raw_bytes: bytes, meta: str | None) -> dict[str, Any]:
    """Parsuje treść załącznika lokalnie bez użycia LLM.

    Args:
        raw_bytes: Zdekodowane bajty załącznika.
        meta: Typ MIME zwrócony przez API.

    Returns:
        Słownik zawierający:
        - content_type: rozpoznany typ treści
        - parsed: sparsowane dane lub None
        - text_preview: fragment tekstu do szybkiej diagnostyki
    """
    text_preview = ""
    content_type = (meta or "").lower().strip()

    if content_type.startswith("image/"):
        return {"content_type": "image", "parsed": None, "text_preview": ""}

    if content_type.startswith("audio/"):
        return {"content_type": "audio", "parsed": None, "text_preview": ""}

    if "json" in content_type:
        text = raw_bytes.decode("utf-8", errors="replace")
        text_preview = text[:500]
        try:
            parsed = json.loads(text)
            return {"content_type": "json", "parsed": parsed, "text_preview": text_preview}
        except json.JSONDecodeError:
            return {"content_type": "json-invalid", "parsed": None, "text_preview": text_preview}

    text = raw_bytes.decode("utf-8", errors="replace")
    text_preview = text[:500]
    return {"content_type": "text", "parsed": text, "text_preview": text_preview}


def extract_facts_from_nested_payload(payload: Any) -> dict[str, Any]:
    """Wydobywa potencjalne fakty z dowolnej zagnieżdżonej struktury JSON.

    Args:
        payload: Struktura danych pochodząca z załącznika.

    Returns:
        Słownik z kandydatami pól raportu.
    """
    collected_strings: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                collected_strings.append(str(key))
                walk(value)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        collected_strings.append(str(node))

    walk(payload)
    combined_text = "\n".join(collected_strings)

    city_name = None
    city_area = None
    warehouses_count = None
    phone_number = None

    city_match = re.search(
        r"(Nowogr[oó]d P[oó][łl]nocny|Syjon|Mielnik|Karlink[oó]w|Domatowo)",
        combined_text,
        re.IGNORECASE,
    )
    if city_match:
        city_name = city_match.group(1)

    area_patterns = [
        r"(?:area|powierzchni[ae]?|cityArea|city_area)\D{0,30}(\d+(?:[.,]\d+)?)",
        r"(\d+(?:[.,]\d+)?)\s*(?:km2|km\^2|km²)",
    ]
    for pattern in area_patterns:
        area_match = re.search(pattern, combined_text, re.IGNORECASE)
        if area_match:
            city_area = area_match.group(1).replace(",", ".")
            break

    warehouses_patterns = [
        r"(?:warehousesCount|warehouse_count)\D{0,20}(\d+)",
        r"(?:warehouses|magazyn(?:y|ow|ów)?)\D{0,30}(\d+)",
        r"(\d+)\D{0,30}(?:warehouses|magazyn(?:y|ow|ów)?)",
    ]
    for pattern in warehouses_patterns:
        warehouses_match = re.search(pattern, combined_text, re.IGNORECASE)
        if warehouses_match:
            warehouses_count = warehouses_match.group(1)
            break

    if warehouses_count is None:
        warehouses_count = _extract_warehouses_count(combined_text)

    phone_match = re.search(r"(?:\+48[\s-]*)?(\d{3}[\s-]?\d{3}[\s-]?\d{3})", combined_text)
    if phone_match:
        phone_number = re.sub(r"\D", "", phone_match.group(1))

    return {
        "cityName": city_name,
        "cityArea": city_area,
        "warehousesCount": warehouses_count,
        "phoneNumber": phone_number,
    }
