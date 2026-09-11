"""Skrypt do rozwiązania podpowiedzi misji pobocznej."""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from config import Settings
from decode_utils import (
    apply_awklike_template_to_json_file,
    extract_recheck_lists,
    fetch_text,
    generate_decode_candidates,
)
from io_utils import write_json, write_text
from verify_client import submit_candidate


def log_step(message: str) -> None:
    """Wypisuje krótki komunikat etapowy do terminala.

    Args:
        message: Treść komunikatu.
    """

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty wejściowe.

    Returns:
        Obiekt z argumentami uruchomienia.
    """

    parser = argparse.ArgumentParser(description="Misja poboczna: analiza podpowiedzi liczbowej")
    parser.add_argument(
        "--hint",
        type=str,
        default=None,
        help="Nadpisuje podpowiedź tekstową z .env (SIDE_HINT_EXPRESSION).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Wysyła kandydatów do /verify i zapisuje odpowiedzi.",
    )
    parser.add_argument(
        "--decode",
        action="store_true",
        help="Uruchamia etap pobrania i dekodowania pliku decode.txt.",
    )
    parser.add_argument(
        "--decode-url",
        type=str,
        default=None,
        help="Nadpisuje URL pliku decode.txt z .env (SIDE_DECODE_URL).",
    )
    return parser.parse_args()


def extract_numbers(expression: str) -> List[int]:
    """Wyciąga liczby całkowite z podpowiedzi.

    Args:
        expression: Tekst podpowiedzi.

    Returns:
        Lista liczb w kolejności wystąpienia.
    """

    return [int(token) for token in re.findall(r"\d+", expression)]


def evaluate_subtraction_chain(numbers: List[int]) -> int:
    """Liczy wynik ciągu odejmowań od lewej do prawej.

    Args:
        numbers: Lista liczb, np. [9132, 1522, 2306].

    Returns:
        Wynik wyrażenia `n1 - n2 - n3 - ...`.

    Raises:
        ValueError: Gdy lista liczb jest pusta.
    """

    if not numbers:
        raise ValueError("Brak liczb do obliczenia.")
    result = numbers[0]
    for value in numbers[1:]:
        result -= value
    return result


def build_recheck_candidates(numbers: List[int]) -> List[Dict[str, List[object]]]:
    """Buduje listę kandydatów odpowiedzi w formacie `answer.recheck`.

    Args:
        numbers: Lista liczb z podpowiedzi.

    Returns:
        Lista kandydatów JSON zgodnych ze schematem zadania.
    """

    ids_str = [f"{value:04d}" for value in numbers]
    ids_int = list(numbers)
    ids_json = [f"{value:04d}.json" for value in numbers]

    candidates: List[Dict[str, List[object]]] = [
        {"recheck": ids_str},
        {"recheck": ids_int},
        {"recheck": ids_json},
    ]
    return candidates


def main() -> None:
    """Uruchamia przepływ: analiza hintu, zapis wyników, opcjonalna weryfikacja."""

    args = parse_args()
    settings = Settings()
    settings.ensure_directories()

    hint = args.hint or settings.hint_expression
    log_step("Start programu misji pobocznej.")
    log_step(f"Podpowiedź: {hint}")

    numbers = extract_numbers(hint)
    result = evaluate_subtraction_chain(numbers)
    candidates = build_recheck_candidates(numbers)

    analysis_payload: Dict[str, object] = {
        "hint": hint,
        "numbers": numbers,
        "operation": "left_to_right_subtraction",
        "result": result,
        "recheck_candidates": candidates,
    }
    write_json(settings.output_dir / "step1_analysis.json", analysis_payload)
    write_text(
        settings.output_dir / "final_result.txt",
        "\n".join([str(candidate) for candidate in candidates]),
    )

    log_step(f"Wynik działania: {result}")
    log_step(f"Kandydaci odpowiedzi (recheck): {candidates}")

    if args.verify:
        if not settings.verify_url:
            log_step("Brak VERIFY_URL, pomijam wysyłkę.")
            return
        if not settings.hub_api_key:
            log_step("Brak HUB_API_KEY, pomijam wysyłkę.")
            return

        log_step("Wysyłanie kandydatów do /verify.")
        responses: List[Dict[str, object]] = []
        for candidate in candidates:
            response = submit_candidate(
                verify_url=settings.verify_url,
                api_key=settings.hub_api_key,
                task_name=settings.side_task_name,
                candidate=candidate,
                timeout_seconds=settings.request_timeout_seconds,
            )
            responses.append({"candidate": candidate, "response": response})
        write_json(settings.output_dir / "verify_responses.json", {"attempts": responses})
        log_step("Zapisano odpowiedzi w output/verify_responses.json")

    if args.decode:
        decode_url = args.decode_url or settings.decode_url
        log_step(f"Pobieranie decode.txt z: {decode_url}")
        decode_raw = fetch_text(decode_url, timeout_seconds=settings.request_timeout_seconds)
        write_text(settings.output_dir / "decode_raw.txt", decode_raw)

        decoded_candidates = generate_decode_candidates(decode_raw)
        write_json(settings.output_dir / "decode_candidates.json", {"candidates": decoded_candidates})
        log_step(f"Wygenerowano kandydatów dekodowania: {len(decoded_candidates)}")

        recheck_candidates: List[Dict[str, List[str]]] = []
        for item in decoded_candidates:
            for recheck_list in extract_recheck_lists(item["text"]):
                recheck_candidates.append({"recheck": recheck_list})

        # Deduplikacja kandydatów recheck.
        unique_recheck: List[Dict[str, List[str]]] = []
        seen = set()
        for candidate in recheck_candidates:
            key = tuple(candidate["recheck"])
            if key in seen:
                continue
            seen.add(key)
            unique_recheck.append(candidate)

        write_json(settings.output_dir / "decode_recheck_candidates.json", {"candidates": unique_recheck})
        write_text(
            settings.output_dir / "decode_recheck_candidates.txt",
            "\n".join([str(item) for item in unique_recheck]),
        )
        log_step(f"Wykryto kandydatów recheck po dekodowaniu: {len(unique_recheck)}")

        # Specjalny przypadek z decode.txt: skrypt AWK z podpowiedzią "awkward".
        # Używamy wyniku odejmowania jako identyfikatora pliku JSON.
        sensors_base = Path(__file__).resolve().parents[1] / "lesson1_evaluation" / "data" / "sensors"
        derived_json = sensors_base / f"{result:04d}.json"
        if derived_json.exists():
            flag = apply_awklike_template_to_json_file(str(derived_json))
            if flag:
                write_text(settings.output_dir / "decode_flag.txt", flag)
                log_step(f"Wyliczona flaga z szablonu AWK: {flag}")

        if args.verify:
            if not settings.verify_url:
                log_step("Brak VERIFY_URL, pomijam weryfikację decode.")
            elif not settings.hub_api_key:
                log_step("Brak HUB_API_KEY, pomijam weryfikację decode.")
            elif not unique_recheck:
                log_step("Brak kandydatów recheck po dekodowaniu, pomijam weryfikację decode.")
            else:
                log_step("Wysyłanie kandydatów decode do /verify.")
                decode_responses: List[Dict[str, object]] = []
                for candidate in unique_recheck:
                    response = submit_candidate(
                        verify_url=settings.verify_url,
                        api_key=settings.hub_api_key,
                        task_name=settings.side_task_name,
                        candidate=candidate,
                        timeout_seconds=settings.request_timeout_seconds,
                    )
                    decode_responses.append({"candidate": candidate, "response": response})
                write_json(
                    settings.output_dir / "decode_verify_responses.json",
                    {"attempts": decode_responses},
                )
                log_step("Zapisano odpowiedzi decode w output/decode_verify_responses.json")

    log_step("Koniec programu.")


if __name__ == "__main__":
    main()
