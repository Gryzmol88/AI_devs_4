"""Narzędzie do dekodowania ukrytych wiadomości z odpowiedzi API.

Skrypt:
1. Szuka fragmentu hex (`aa,bb,cc,...`) i dekoduje go do UTF-8.
2. Wyodrębnia treść po separatorze `---` (jeśli istnieje).
3. Wykonuje serię prób dekodowania (Vigenere i Caesar).
4. Opcjonalnie uruchamia `auto-chain`, gdzie najlepsze wyniki stają się wejściem
   dla kolejnych rund.
5. Zapisuje wyniki do `output/<timestamp>/decoder_result.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import string
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

FLAG_RE = re.compile(r"\{FLG:[^}]+\}")
HEX_RE = re.compile(r"(?:[0-9a-fA-F]{2},){8,}[0-9a-fA-F]{2}")
URL_HINT_RE = re.compile(r"(https?://|://|\.org|\.com|\.net|\.io|\.pl|\.mp4)", re.IGNORECASE)

ALPHABET = string.ascii_lowercase
DEFAULT_KEYS = [
    "blaise",
    "blazej",
    "błażej",
    "vigenere",
    "blaisedevigenere",
    "azazel",
]


@dataclass(slots=True)
class DecodeAttempt:
    """Reprezentuje pojedynczą próbę dekodowania.

    Attributes:
        step: Numer kroku.
        key: Użyty klucz.
        mode: Tryb transformacji.
        text: Tekst wynikowy.
        score: Heurystyczna ocena jakości.
        found_flag: Znaleziona flaga `{FLG:...}`.
    """

    step: int
    key: str
    mode: str
    text: str
    score: int
    found_flag: str


def now_ts() -> str:
    """Zwraca znacznik czasu dla katalogu wynikowego.

    Returns:
        str: Znacznik czasu `YYYYMMDD_HHMMSS_microseconds`.
    """

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def normalize_ascii(text: str) -> str:
    """Normalizuje tekst do wariantu ASCII.

    Args:
        text: Tekst wejściowy.

    Returns:
        str: Tekst po normalizacji Unicode NFKD.
    """

    return "".join(
        char for char in unicodedata.normalize("NFKD", text) if not unicodedata.combining(char)
    )


def extract_hex_blob(raw_text: str) -> str:
    """Wyszukuje największy fragment hex oddzielony przecinkami.

    Args:
        raw_text: Surowa treść wejściowa.

    Returns:
        str: Fragment hex (`aa,bb,...`) lub pusty string.
    """

    matches = HEX_RE.findall(raw_text)
    if not matches:
        return ""
    return max(matches, key=len)


def decode_hex_csv(hex_blob: str) -> str:
    """Dekoduje CSV hex do UTF-8.

    Args:
        hex_blob: Ciąg hex oddzielony przecinkami.

    Returns:
        str: Zdekodowany tekst UTF-8.

    Raises:
        ValueError: Gdy hex blob jest pusty lub błędny.
    """

    if not hex_blob:
        raise ValueError("Brak ciagu hex do dekodowania.")
    data = bytes(int(item, 16) for item in hex_blob.split(","))
    return data.decode("utf-8")


def extract_payload_for_cipher(decoded_text: str) -> str:
    """Wyodrębnia treść do dalszego dekodowania.

    Args:
        decoded_text: Tekst po dekodowaniu hex.

    Returns:
        str: Treść po `---` lub cały tekst.
    """

    if "---" in decoded_text:
        return decoded_text.split("---", 1)[1].strip()
    return decoded_text.strip()


def find_flag(text: str) -> str:
    """Wyszukuje flagę `{FLG:...}` w tekście.

    Args:
        text: Tekst wejściowy.

    Returns:
        str: Flaga lub pusty string.
    """

    match = FLAG_RE.search(text)
    return match.group(0) if match else ""


def score_text(text: str) -> int:
    """Oblicza heurystyczny score jakości.

    Args:
        text: Tekst do oceny.

    Returns:
        int: Wynik punktowy.
    """

    score = 0
    if find_flag(text):
        score += 1000
    if URL_HINT_RE.search(text):
        score += 100
    common_words = ["jak", "osoba", "znalezion", "http", "https", "ag3", "domatowo", "flg"]
    low = text.lower()
    score += sum(15 for word in common_words if word in low)
    printable_ratio = sum(1 for ch in text if ch.isprintable()) / max(1, len(text))
    score += int(printable_ratio * 20)
    return score


def vigenere_decrypt(text: str, key: str) -> str:
    """Deszyfruje tekst szyfrem Vigenere.

    Args:
        text: Szyfrogram.
        key: Klucz szyfru (a-z).

    Returns:
        str: Odszyfrowana treść.
    """

    output: list[str] = []
    key_index = 0
    normalized_key = "".join(ch for ch in normalize_ascii(key).lower() if ch in ALPHABET)
    if not normalized_key:
        return text

    for char in text:
        lower = char.lower()
        if lower in ALPHABET:
            shift = ALPHABET.index(normalized_key[key_index % len(normalized_key)])
            base = ord("A") if char.isupper() else ord("a")
            decoded = chr((ord(char) - base - shift) % 26 + base)
            output.append(decoded)
            key_index += 1
        else:
            output.append(char)
    return "".join(output)


def caesar_decrypt(text: str, shift: int) -> str:
    """Deszyfruje tekst szyfrem Cezara.

    Args:
        text: Szyfrogram.
        shift: Przesunięcie 0-25.

    Returns:
        str: Odszyfrowana treść.
    """

    output: list[str] = []
    for char in text:
        lower = char.lower()
        if lower in ALPHABET:
            base = ord("A") if char.isupper() else ord("a")
            decoded = chr((ord(char) - base - shift) % 26 + base)
            output.append(decoded)
        else:
            output.append(char)
    return "".join(output)


def run_decode_pipeline(payload: str, keys: list[str], depth: int) -> list[DecodeAttempt]:
    """Uruchamia jedną rundę dekodowania.

    Args:
        payload: Tekst wejściowy.
        keys: Klucze Vigenere.
        depth: Liczba warstw Vigenere na klucz.

    Returns:
        list[DecodeAttempt]: Lista prób posortowana malejąco po score.
    """

    attempts: list[DecodeAttempt] = []
    step = 0
    base_text = normalize_ascii(payload)
    attempts.append(
        DecodeAttempt(
            step=step,
            key="",
            mode="raw_normalized",
            text=base_text,
            score=score_text(base_text),
            found_flag=find_flag(base_text),
        )
    )
    step += 1

    for key in keys:
        current = base_text
        for layer in range(1, depth + 1):
            current = vigenere_decrypt(current, key)
            attempts.append(
                DecodeAttempt(
                    step=step,
                    key=key,
                    mode=f"vigenere_dec_layer_{layer}",
                    text=current,
                    score=score_text(current),
                    found_flag=find_flag(current),
                )
            )
            step += 1

    for shift in range(26):
        text = caesar_decrypt(base_text, shift)
        attempts.append(
            DecodeAttempt(
                step=step,
                key=str(shift),
                mode="caesar_dec",
                text=text,
                score=score_text(text),
                found_flag=find_flag(text),
            )
        )
        step += 1

    attempts.sort(key=lambda item: item.score, reverse=True)
    return attempts


def run_auto_chain(
    payload: str,
    keys: list[str],
    depth: int,
    rounds: int,
    branch_width: int,
) -> dict[str, Any]:
    """Uruchamia wielorundowe dekodowanie z rozwijaniem najlepszych kandydatów.

    Args:
        payload: Tekst startowy.
        keys: Klucze Vigenere.
        depth: Głębokość Vigenere per runda.
        rounds: Maksymalna liczba rund.
        branch_width: Liczba kandydatów przenoszonych dalej.

    Returns:
        dict[str, Any]: Dane rund, najlepszy globalny wynik i znalezione flagi.
    """

    queue: list[str] = [payload]
    visited: set[str] = {payload}
    rounds_data: list[dict[str, Any]] = []
    flags_found: set[str] = set()
    best_global: DecodeAttempt | None = None

    for round_index in range(1, rounds + 1):
        if not queue:
            break
        current_sources = queue
        queue = []

        for source_index, source_text in enumerate(current_sources, start=1):
            attempts = run_decode_pipeline(payload=source_text, keys=keys, depth=depth)
            top_attempts = attempts[:20]
            rounds_data.append(
                {
                    "round": round_index,
                    "sourceIndex": source_index,
                    "sourceText": source_text,
                    "topAttempts": [
                        {
                            "step": item.step,
                            "mode": item.mode,
                            "key": item.key,
                            "score": item.score,
                            "foundFlag": item.found_flag,
                            "text": item.text,
                        }
                        for item in top_attempts
                    ],
                }
            )

            for attempt in attempts:
                if attempt.found_flag:
                    flags_found.add(attempt.found_flag)
                if best_global is None or attempt.score > best_global.score:
                    best_global = attempt

            for candidate in attempts[:branch_width]:
                if candidate.text not in visited:
                    visited.add(candidate.text)
                    queue.append(candidate.text)

        if flags_found:
            break

    return {
        "roundsData": rounds_data,
        "flagsFound": sorted(flags_found),
        "bestGlobal": None
        if best_global is None
        else {
            "step": best_global.step,
            "mode": best_global.mode,
            "key": best_global.key,
            "score": best_global.score,
            "foundFlag": best_global.found_flag,
            "text": best_global.text,
        },
    }


def load_input_text(args: argparse.Namespace) -> str:
    """Wczytuje tekst wejściowy na podstawie argumentów CLI.

    Args:
        args: Sparsowane argumenty.

    Returns:
        str: Tekst wejściowy.

    Raises:
        ValueError: Gdy nie podano źródła wejścia.
    """

    if args.input_text:
        return args.input_text
    if args.input_file:
        return Path(args.input_file).read_text(encoding="utf-8")
    raise ValueError("Podaj --input-text albo --input-file.")


def build_arg_parser() -> argparse.ArgumentParser:
    """Buduje parser argumentów CLI.

    Returns:
        argparse.ArgumentParser: Skonfigurowany parser.
    """

    parser = argparse.ArgumentParser(description="Dekoder sekretów lesson3_misja_poboczna")
    parser.add_argument("--input-text", type=str, help="Surowy tekst lub cały msg z API.")
    parser.add_argument("--input-file", type=str, help="Plik z surową treścią do dekodowania.")
    parser.add_argument(
        "--keys",
        type=str,
        default=",".join(DEFAULT_KEYS),
        help="Lista kluczy Vigenere oddzielona przecinkami.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maksymalna liczba warstw Vigenere na klucz.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output",
        help="Bazowy katalog output (względny do lesson3_misja_poboczna).",
    )
    parser.add_argument(
        "--auto-chain",
        action="store_true",
        help="Uruchamia wielorundowe dekodowanie z najlepszych kandydatów.",
    )
    parser.add_argument(
        "--chain-rounds",
        type=int,
        default=4,
        help="Maksymalna liczba rund auto-chain.",
    )
    parser.add_argument(
        "--branch-width",
        type=int,
        default=3,
        help="Liczba kandydatów przenoszonych do kolejnej rundy.",
    )
    return parser


def main() -> None:
    """Uruchamia proces dekodowania i zapisuje wynik do output.

    Returns:
        None: Funkcja drukuje podsumowanie i zapisuje pliki na dysku.
    """

    parser = build_arg_parser()
    args = parser.parse_args()

    raw_text = load_input_text(args)
    keys = [key.strip() for key in args.keys.split(",") if key.strip()]

    output_base = Path(__file__).resolve().parent / args.output_dir
    run_dir = output_base / now_ts()
    run_dir.mkdir(parents=True, exist_ok=True)
    (output_base / "latest_decoder_run.txt").write_text(str(run_dir), encoding="utf-8")

    hex_blob = extract_hex_blob(raw_text)
    decoded_hex_text = decode_hex_csv(hex_blob) if hex_blob else raw_text
    payload = extract_payload_for_cipher(decoded_hex_text)

    attempts = run_decode_pipeline(payload=payload, keys=keys, depth=args.depth)
    top_attempts = attempts[:20]
    found_flags = {item.found_flag for item in attempts if item.found_flag}

    auto_chain_result: dict[str, Any] | None = None
    if args.auto_chain:
        auto_chain_result = run_auto_chain(
            payload=payload,
            keys=keys,
            depth=args.depth,
            rounds=args.chain_rounds,
            branch_width=args.branch_width,
        )
        for flag in auto_chain_result.get("flagsFound", []):
            if isinstance(flag, str) and flag:
                found_flags.add(flag)

    result: dict[str, Any] = {
        "generatedAt": datetime.now().isoformat(timespec="milliseconds"),
        "keys": keys,
        "depth": args.depth,
        "autoChain": args.auto_chain,
        "chainRounds": args.chain_rounds,
        "branchWidth": args.branch_width,
        "hexFound": bool(hex_blob),
        "hexBlob": hex_blob,
        "decodedHexText": decoded_hex_text,
        "payloadForCipher": payload,
        "topAttempts": [
            {
                "step": item.step,
                "mode": item.mode,
                "key": item.key,
                "score": item.score,
                "foundFlag": item.found_flag,
                "text": item.text,
            }
            for item in top_attempts
        ],
        "flagsFound": sorted(found_flags),
    }
    if auto_chain_result is not None:
        result["autoChainResult"] = auto_chain_result

    (run_dir / "decoder_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    best = top_attempts[0] if top_attempts else None
    print(f"[decoder] Output run: {run_dir}")
    if best:
        print(f"[decoder] Best mode={best.mode} key={best.key} score={best.score}")
        print(f"[decoder] Best text: {best.text}")
    if auto_chain_result is not None and auto_chain_result.get("bestGlobal"):
        best_global = auto_chain_result["bestGlobal"]
        print(
            "[decoder] Auto-chain best "
            f"mode={best_global['mode']} key={best_global['key']} score={best_global['score']}"
        )
        print(f"[decoder] Auto-chain text: {best_global['text']}")
    if result["flagsFound"]:
        print(f"[decoder] FLAGS: {result['flagsFound']}")


if __name__ == "__main__":
    main()
