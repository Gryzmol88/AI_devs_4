"""Skrypt misji pobocznej lesson3: Take Me to Church."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from config import AppSettings

FLAG_PATTERN = re.compile(r"\{FLG:[^}]+\}")
CELL_PATTERN = re.compile(r"^[A-K](?:10|11|[1-9])$")


def log_info(message: str) -> None:
    """Wypisuje krótki komunikat statusowy do terminala.

    Args:
        message: Treść komunikatu.

    Returns:
        None: Funkcja wykonuje wyłącznie efekt uboczny I/O.
    """

    print(f"[lesson3_misja_poboczna] {message}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Zapisuje dane do pliku JSON.

    Args:
        path: Docelowa ścieżka pliku.
        payload: Dane do serializacji.

    Returns:
        None: Funkcja zapisuje plik na dysku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def now_ts() -> str:
    """Zwraca znacznik czasu dla nazw katalogów output.

    Returns:
        str: Znacznik czasu `YYYYMMDD_HHMMSS_microseconds`.
    """

    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


class VerifyApiClient:
    """Klient API `/verify` dla zadania `domatowo`.

    Klasa odpowiada za wysyłkę akcji oraz rejestrację trace request/response.
    """

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Ustawienia aplikacji.
        """

        self._settings = settings
        self._session = requests.Session()

    def call(self, answer: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Wysyła pojedynczą akcję do API.

        Args:
            answer: Pole `answer` zgodne ze specyfikacją zadania.

        Returns:
            tuple[dict[str, Any], dict[str, Any]]: Odpowiedź API i trace żądania.

        Raises:
            RuntimeError: Gdy API zwróci błąd HTTP.
        """

        payload = {
            "apikey": self._settings.aidevs_api_key,
            "task": self._settings.domatowo_task,
            "answer": answer,
        }
        started_at = datetime.now().isoformat(timespec="milliseconds")
        response = self._session.post(
            self._settings.aidevs_verify_url,
            json=payload,
            timeout=self._settings.app_timeout_seconds,
        )
        finished_at = datetime.now().isoformat(timespec="milliseconds")
        try:
            response_payload = response.json()
        except Exception:  # noqa: BLE001
            response_payload = {"rawText": response.text}

        trace = {
            "startedAt": started_at,
            "finishedAt": finished_at,
            "request": {"answer": answer},
            "http": {"statusCode": response.status_code, "ok": response.ok},
            "response": response_payload,
        }
        if not response.ok:
            raise RuntimeError(
                f"Blad HTTP dla akcji {answer}: status={response.status_code}, body={response.text}"
            )
        return response_payload, trace


def extract_church_cells(search_ks_payload: dict[str, Any], map_payload: dict[str, Any]) -> list[str]:
    """Wyznacza pola kościoła na podstawie `searchSymbol(KS)` i fallbacku z mapy.

    Args:
        search_ks_payload: Odpowiedź API z `searchSymbol` dla `KS`.
        map_payload: Odpowiedź API z `getMap`.

    Returns:
        list[str]: Unikalna lista pól kościoła.
    """

    from_search: list[str] = []
    found = search_ks_payload.get("found")
    if isinstance(found, list):
        for item in found:
            if not isinstance(item, dict):
                continue
            position = item.get("position")
            if isinstance(position, str) and CELL_PATTERN.match(position):
                from_search.append(position)

    from_map: list[str] = []
    map_node = map_payload.get("map", {})
    grid = map_node.get("grid", [])
    if isinstance(grid, list):
        for row_idx, row in enumerate(grid):
            if not isinstance(row, list):
                continue
            for col_idx, tile in enumerate(row):
                if tile == "church":
                    cell = f"{chr(ord('A') + col_idx)}{row_idx + 1}"
                    from_map.append(cell)

    return list(dict.fromkeys(from_search + from_map))


def cell_to_row_col(cell: str) -> tuple[int, int]:
    """Konwertuje pole typu `F7` na współrzędne liczbowe.

    Args:
        cell: Pole mapy.

    Returns:
        tuple[int, int]: Wiersz i kolumna indeksowane od zera.
    """

    return int(cell[1:]) - 1, ord(cell[0]) - ord("A")


def manhattan(a: str, b: str) -> int:
    """Liczy odległość Manhattan między dwoma polami.

    Args:
        a: Pole startowe.
        b: Pole docelowe.

    Returns:
        int: Odległość ortogonalna.
    """

    ar, ac = cell_to_row_col(a)
    br, bc = cell_to_row_col(b)
    return abs(ar - br) + abs(ac - bc)


def order_cells_nearest(start_cell: str, cells: list[str]) -> list[str]:
    """Porządkuje pola heurystyką najbliższego sąsiada.

    Args:
        start_cell: Pole startowe zwiadowcy.
        cells: Lista pól do sprawdzenia.

    Returns:
        list[str]: Pola w kolejności przeszukania.
    """

    ordered: list[str] = []
    current = start_cell
    remaining = list(cells)
    while remaining:
        next_cell = min(remaining, key=lambda cell: manhattan(current, cell))
        ordered.append(next_cell)
        remaining.remove(next_cell)
        current = next_cell
    return ordered


def find_flags(payload: Any) -> list[str]:
    """Wyszukuje potencjalne sekrety w dowolnym payloadzie API.

    Args:
        payload: Odpowiedź API lub jej fragment.

    Returns:
        list[str]: Lista dopasowanych sekretów `{FLG:...}`.
    """

    text = json.dumps(payload, ensure_ascii=False)
    return FLAG_PATTERN.findall(text)


def append_trace_line(path: Path, trace: dict[str, Any]) -> None:
    """Dopisuje pojedynczy rekord trace do pliku NDJSON.

    Args:
        path: Ścieżka pliku NDJSON.
        trace: Rekord trace do dopisania.

    Returns:
        None: Funkcja zapisuje wpis do pliku.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, ensure_ascii=False) + "\n")


def run() -> dict[str, Any]:
    """Wykonuje scenariusz poboczny: pełne przeszukanie pól kościoła.

    Returns:
        dict[str, Any]: Podsumowanie działania i wykrytych sekretów.

    Effects:
        Tworzy katalog output z timestamp, zapisuje trace i pliki kroków.
    """

    settings = AppSettings()
    output_base = settings.output_path
    run_dir = output_base / now_ts()
    run_dir.mkdir(parents=True, exist_ok=True)
    (output_base / "latest_run.txt").write_text(str(run_dir), encoding="utf-8")

    log_info(f"Task: {settings.domatowo_task}")
    log_info(f"Katalog output runu: {run_dir}")
    log_info("Wskazowka: Take Me to Church")

    client = VerifyApiClient(settings)
    live_trace_path = run_dir / "live_trace.ndjson"

    traces: list[dict[str, Any]] = []
    found_flags: list[str] = []

    def call_and_save(step_name: str, answer: dict[str, Any]) -> dict[str, Any]:
        """Wysyła akcję do API i zapisuje trace oraz snapshot kroku.

        Args:
            step_name: Nazwa kroku zapisywana w output.
            answer: Payload `answer` wysyłany do API.

        Returns:
            dict[str, Any]: Odpowiedź API.
        """

        response_payload, trace = client.call(answer)
        trace["step"] = step_name
        traces.append(trace)
        append_trace_line(live_trace_path, trace)
        write_json(run_dir / f"{step_name}.json", response_payload)
        found_flags.extend(find_flags(response_payload))
        return response_payload

    log_info("Reset planszy")
    call_and_save("step0_reset", {"action": "reset"})
    log_info("Pobieranie mapy i listy pol kosciola")
    map_payload = call_and_save("step1_get_map", {"action": "getMap"})
    ks_payload = call_and_save("step2_search_ks", {"action": "searchSymbol", "symbol": "KS"})
    church_cells = extract_church_cells(ks_payload, map_payload)
    if not church_cells:
        summary = {
            "status": "failed",
            "reason": "Nie znaleziono pol kosciola.",
            "runDir": str(run_dir),
            "flags": [],
        }
        write_json(run_dir / "final_result.json", summary)
        return summary

    log_info(f"Tworzenie zwiadowcy i przeszukanie pol KS ({len(church_cells)})")
    create_payload = call_and_save("step3_create_scout", {"action": "create", "type": "scout"})
    scout_id = str(create_payload.get("object", ""))
    scout_spawn = str(create_payload.get("spawn", "A6"))
    ordered_cells = order_cells_nearest(scout_spawn, church_cells)
    write_json(
        run_dir / "step4_plan_church_cells.json",
        {
            "churchCells": church_cells,
            "orderedCells": ordered_cells,
            "scoutObject": scout_id,
            "scoutSpawn": scout_spawn,
        },
    )

    inspected: list[dict[str, Any]] = []
    for index, cell in enumerate(ordered_cells, start=1):
        log_info(f"[{index}/{len(ordered_cells)}] Ruch i inspekcja pola {cell}")
        move_payload = call_and_save(
            f"step5_move_{index:02d}_{cell}",
            {"action": "move", "object": scout_id, "where": cell},
        )
        inspect_payload = call_and_save(
            f"step6_inspect_{index:02d}_{cell}",
            {"action": "inspect", "object": scout_id},
        )
        logs_payload = call_and_save(f"step7_logs_{index:02d}_{cell}", {"action": "getLogs"})
        inspected.append(
            {
                "cell": cell,
                "move": move_payload,
                "inspect": inspect_payload,
                "logs": logs_payload,
            }
        )

    unique_flags = sorted(set(found_flags))
    summary = {
        "status": "ok",
        "task": settings.domatowo_task,
        "hint": "Take Me to Church",
        "runDir": str(run_dir),
        "scoutObject": scout_id,
        "churchCellsCount": len(church_cells),
        "churchCells": church_cells,
        "inspectedCount": len(inspected),
        "flagsFound": bool(unique_flags),
        "flags": unique_flags,
    }
    write_json(run_dir / "step8_inspection_summary.json", {"inspected": inspected})
    write_json(run_dir / "final_result.json", summary)
    return summary


def main() -> None:
    """Uruchamia skrypt i wypisuje końcowe podsumowanie.

    Returns:
        None: Funkcja uruchamia pełny przebieg i drukuje wynik.
    """

    result = run()
    log_info(f"Wynik koncowy: {result}")


if __name__ == "__main__":
    main()

