"""Narzędzia do pobierania i dekodowania treści decode.txt."""

from __future__ import annotations

import base64
import binascii
import bz2
import codecs
import gzip
import json
import lzma
import re
import zlib
from typing import Dict, List, Tuple
from urllib.request import urlopen


def fetch_text(url: str, timeout_seconds: int = 30) -> str:
    """Pobiera tekst z podanego URL.

    Args:
        url: Adres źródła tekstu.
        timeout_seconds: Limit czasu żądania.

    Returns:
        Treść odpowiedzi jako tekst UTF-8.
    """

    with urlopen(url, timeout=timeout_seconds) as response:  # nosec: B310
        raw = response.read()
    return raw.decode("utf-8", errors="replace")


def _decode_base64_to_text(value: str) -> str:
    """Dekoduje tekst base64 do UTF-8."""

    normalized = value.strip()
    padding = "=" * (-len(normalized) % 4)
    data = base64.b64decode(normalized + padding, validate=False)
    return data.decode("utf-8", errors="replace")


def _decode_hex_to_text(value: str) -> str:
    """Dekoduje tekst hex do UTF-8."""

    cleaned = re.sub(r"[^0-9a-fA-F]", "", value)
    data = bytes.fromhex(cleaned)
    return data.decode("utf-8", errors="replace")


def _try_decompress_bytes(data: bytes) -> List[Tuple[str, str]]:
    """Próbuje różnych algorytmów dekompresji dla surowych bajtów."""

    results: List[Tuple[str, str]] = []
    decompressors = [
        ("gzip", gzip.decompress),
        ("zlib", zlib.decompress),
        ("bz2", bz2.decompress),
        ("lzma", lzma.decompress),
    ]
    for label, func in decompressors:
        try:
            text = func(data).decode("utf-8", errors="replace")
            results.append((f"decompress_{label}", text))
        except Exception:
            continue
    return results


def generate_decode_candidates(raw_text: str) -> List[Dict[str, str]]:
    """Generuje kandydatów dekodowania dla przekazanej treści.

    Args:
        raw_text: Surowa treść pliku decode.txt.

    Returns:
        Lista kandydatów w postaci słowników `{"method": ..., "text": ...}`.
    """

    candidates: List[Tuple[str, str]] = [("raw", raw_text)]
    stripped = raw_text.strip()

    try:
        candidates.append(("base64", _decode_base64_to_text(stripped)))
    except Exception:
        pass

    try:
        candidates.append(("base64_urlsafe", base64.urlsafe_b64decode(stripped + "=" * (-len(stripped) % 4)).decode("utf-8", errors="replace")))
    except Exception:
        pass

    try:
        candidates.append(("hex", _decode_hex_to_text(stripped)))
    except Exception:
        pass

    candidates.append(("rot13", codecs.decode(raw_text, "rot_13")))
    candidates.append(("reversed", raw_text[::-1]))

    # Próby dekompresji bezpośrednio na surowym tekście i na base64/hex.
    raw_bytes = raw_text.encode("utf-8", errors="replace")
    candidates.extend(_try_decompress_bytes(raw_bytes))

    try:
        b64_bytes = base64.b64decode(stripped + "=" * (-len(stripped) % 4), validate=False)
        candidates.extend(_try_decompress_bytes(b64_bytes))
    except Exception:
        pass

    try:
        hex_bytes = bytes.fromhex(re.sub(r"[^0-9a-fA-F]", "", stripped))
        candidates.extend(_try_decompress_bytes(hex_bytes))
    except Exception:
        pass

    # Próba dekodowania sekwencji liczb ASCII, np. "65-66-67".
    numbers = re.findall(r"\d{2,3}", raw_text)
    if numbers:
        try:
            ascii_text = "".join(chr(int(value)) for value in numbers if 0 <= int(value) <= 255)
            if ascii_text:
                candidates.append(("ascii_codes", ascii_text))
        except Exception:
            pass

    # Usuwamy duplikaty po treści.
    unique: List[Dict[str, str]] = []
    seen_texts = set()
    for method, text in candidates:
        normalized = text.strip()
        if not normalized or normalized in seen_texts:
            continue
        seen_texts.add(normalized)
        unique.append({"method": method, "text": normalized})
    return unique


def extract_recheck_lists(text: str) -> List[List[str]]:
    """Wyciąga potencjalne listy identyfikatorów do pola `recheck`.

    Args:
        text: Tekst po dekodowaniu.

    Returns:
        Lista kandydatów list ID (jako stringi 4-cyfrowe).
    """

    candidates: List[List[str]] = []

    # 1) JSON z polem recheck.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and "recheck" in parsed and isinstance(parsed["recheck"], list):
            ids = [str(value).replace(".json", "").zfill(4) for value in parsed["recheck"]]
            if ids:
                candidates.append(ids)
    except Exception:
        pass

    # 2) Proste wyłuskanie czterocyfrowych identyfikatorów.
    found_ids = re.findall(r"\b\d{4}\b", text)
    if found_ids:
        ordered_unique = list(dict.fromkeys(found_ids))
        candidates.append(ordered_unique)

    # 3) Identyfikatory z rozszerzeniem .json.
    found_json_ids = re.findall(r"\b(\d{4})\.json\b", text)
    if found_json_ids:
        ordered_unique = list(dict.fromkeys(found_json_ids))
        candidates.append(ordered_unique)

    # Deduplikacja list.
    deduped: List[List[str]] = []
    seen = set()
    for item in candidates:
        key = tuple(item)
        if key in seen or not item:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def apply_awklike_template_to_json_file(json_path: str) -> str:
    """Symuluje działanie skryptu AWK z decode.txt na wskazanym pliku JSON.

    Args:
        json_path: Ścieżka do pliku JSON.

    Returns:
        Wyliczona flaga w formacie `{FLG:...}`.
    """

    with open(json_path, "r", encoding="utf-8") as file:
        lines = file.read().splitlines()

    if len(lines) < 9:
        return ""

    line3_parts = lines[2].split('"')
    line9_parts = lines[8].split('"')
    if len(line3_parts) < 2 or len(line9_parts) < 4:
        return ""

    a = line3_parts[1][:4]
    s = line9_parts[3]
    positions = [44, 60, 66, 74, 76]
    try:
        b = "".join(s[pos - 1] for pos in positions)
    except Exception:
        return ""

    return f"{{FLG:{a.upper()}{b.upper()}}}"
