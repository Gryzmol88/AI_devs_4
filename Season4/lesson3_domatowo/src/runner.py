"""Orkiestracja całego procesu rozwiązania zadania domatowo."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .agents.intel_agent import IntelAgent
from .api_client import Ag3ntsApiClient
from .config import AppSettings
from .models import MissionState, Unit

_CELL_PATTERN = re.compile(r"^[A-K](?:10|11|[1-9])$")


def _print_status(message: str) -> None:
    """Wypisuje krótki komunikat etapowy do terminala.

    Args:
        message: Treść komunikatu statusowego.

    Returns:
        None: Funkcja wykonuje wyłącznie efekt uboczny I/O.
    """

    print(f"[domatowo] {message}")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Zapisuje słownik do pliku JSON.

    Args:
        path: Docelowa ścieżka pliku.
        payload: Dane do serializacji.

    Returns:
        None: Funkcja zapisuje dane na dysku.

    Effects:
        Tworzy brakujące katalogi i zapisuje plik JSON z wcięciami.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _cell_to_row_col(cell: str) -> tuple[int, int]:
    """Konwertuje etykietę pola (np. `F6`) na indeksy wiersza i kolumny.

    Args:
        cell: Etykieta pola mapy.

    Returns:
        tuple[int, int]: Para `(row, col)` indeksowana od zera.
    """

    col = ord(cell[0].upper()) - ord("A")
    row = int(cell[1:]) - 1
    return row, col


def _manhattan_distance(from_cell: str, to_cell: str) -> int:
    """Oblicza dystans Manhattan między dwoma polami planszy.

    Args:
        from_cell: Pole startowe.
        to_cell: Pole docelowe.

    Returns:
        int: Dystans ortogonalny między polami.
    """

    from_row, from_col = _cell_to_row_col(from_cell)
    to_row, to_col = _cell_to_row_col(to_cell)
    return abs(from_row - to_row) + abs(from_col - to_col)


def _extract_positions_from_search_symbol(payload: dict[str, Any]) -> list[str]:
    """Wyciąga pola `position` z odpowiedzi akcji `searchSymbol`.

    Args:
        payload: Odpowiedź JSON z akcji `searchSymbol`.

    Returns:
        list[str]: Lista unikalnych współrzędnych pozycji.
    """

    found = payload.get("found")
    if not isinstance(found, list):
        return []
    positions: list[str] = []
    for item in found:
        if not isinstance(item, dict):
            continue
        position = item.get("position")
        if isinstance(position, str) and _CELL_PATTERN.match(position):
            positions.append(position)
    return list(dict.fromkeys(positions))


def _extract_block3_cells_from_map(map_payload: dict[str, Any]) -> list[str]:
    """Zwraca pola, które na mapie są oznaczone jako `block3`.

    Args:
        map_payload: Odpowiedź z akcji `getMap`.

    Returns:
        list[str]: Lista współrzędnych pól o typie `block3`.
    """

    map_node = map_payload.get("map", {})
    grid = map_node.get("grid", [])
    if not isinstance(grid, list):
        return []

    cells: list[str] = []
    for row_idx, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for col_idx, tile in enumerate(row):
            if tile == "block3":
                cell = f"{chr(ord('A') + col_idx)}{row_idx + 1}"
                cells.append(cell)
    return cells


def _extract_cells_by_tile_from_map(map_payload: dict[str, Any], tile_name: str) -> list[str]:
    """Zwraca pola mapy odpowiadające wskazanemu typowi kafla.

    Args:
        map_payload: Odpowiedź z akcji `getMap`.
        tile_name: Nazwa kafla w `map.grid`, np. `school` lub `church`.

    Returns:
        list[str]: Lista współrzędnych pól dla danego typu kafla.
    """

    map_node = map_payload.get("map", {})
    grid = map_node.get("grid", [])
    if not isinstance(grid, list):
        return []
    cells: list[str] = []
    for row_idx, row in enumerate(grid):
        if not isinstance(row, list):
            continue
        for col_idx, tile in enumerate(row):
            if tile == tile_name:
                cell = f"{chr(ord('A') + col_idx)}{row_idx + 1}"
                cells.append(cell)
    return cells


def _extract_action_points_left(payload: dict[str, Any]) -> int | None:
    """Odczytuje liczbę pozostałych punktów akcji z odpowiedzi API.

    Args:
        payload: Odpowiedź JSON z akcji API.

    Returns:
        int | None: Wartość punktów akcji lub `None`, gdy brak pola.
    """

    value = payload.get("action_points_left")
    if isinstance(value, int):
        return value
    return None


def _contains_target_signal(payload: Any) -> bool:
    """Sprawdza, czy odpowiedź API sugeruje odnalezienie partyzanta.

    Args:
        payload: Dowolna struktura odpowiedzi JSON.

    Returns:
        bool: `True` gdy treść zawiera sygnał znalezienia człowieka.
    """

    text = json.dumps(payload, ensure_ascii=False).lower()
    negative_hints = [
        "no human",
        "not found",
        "brak czlow",
        "brak człow",
        "nie znaleziono",
        "nie odnaleziono",
        "no partisan",
    ]
    if any(hint in text for hint in negative_hints):
        return False

    positive_hints = [
        "found human",
        "human confirmed",
        "osoba potwierdzona",
        "potwierdzona",
        "znaleźliśmy osobę",
        "znalezlismy osobe",
        "znaleziono osobę",
        "znaleziono osobe",
        "partisan found",
        "survivor found",
        "jest człowiek",
        "jest czlowiek",
        "czlowiek odnaleziony",
        "człowiek odnaleziony",
        "odnaleziono czlow",
        "odnaleziono człow",
    ]
    return any(hint in text for hint in positive_hints)


def _extract_logs(payload: dict[str, Any]) -> list[Any]:
    """Wyciąga listę wpisów logów z odpowiedzi `getLogs`.

    Args:
        payload: Odpowiedź JSON z akcji `getLogs`.

    Returns:
        list[Any]: Lista wpisów logów lub pusta lista.
    """

    for key in ("logs", "entries", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
    return []


def _latest_log_for_scout(log_entries: list[Any], scout_id: str) -> dict[str, Any]:
    """Zwraca najnowszy wpis logu dla wskazanego zwiadowcy.

    Args:
        log_entries: Lista wpisów logów zwróconych przez `getLogs`.
        scout_id: Hash obiektu zwiadowcy.

    Returns:
        dict[str, Any]: Najnowszy wpis dla zwiadowcy lub pusty słownik.
    """

    for entry in reversed(log_entries):
        if isinstance(entry, dict) and str(entry.get("scout", "")) == scout_id:
            return entry
    return {}


def _split_block3_clusters(cells: list[str]) -> tuple[list[str], list[str]]:
    """Dzieli pola B3 na klaster północny i południowy.

    Args:
        cells: Lista pól B3.

    Returns:
        tuple[list[str], list[str]]: Krotka `(north_cells, south_cells)`.
    """

    north_cells: list[str] = []
    south_cells: list[str] = []
    for cell in cells:
        row, _ = _cell_to_row_col(cell)
        if row <= 1:
            north_cells.append(cell)
        else:
            south_cells.append(cell)
    return north_cells, south_cells


def _order_cells_nearest(start_cell: str, cells: list[str]) -> list[str]:
    """Porządkuje pola heurystyką najbliższego sąsiada od wskazanego startu.

    Args:
        start_cell: Pole startowe zwiadowcy.
        cells: Lista pól do odwiedzenia.

    Returns:
        list[str]: Lista pól w kolejności przeszukania.
    """

    current = start_cell
    remaining = list(cells)
    ordered: list[str] = []
    while remaining:
        next_cell = min(remaining, key=lambda cell: _manhattan_distance(current, cell))
        ordered.append(next_cell)
        remaining.remove(next_cell)
        current = next_cell
    return ordered


def _find_positive_log_for_scout(log_entries: list[Any], scout_id: str) -> dict[str, Any]:
    """Wyszukuje najnowszy pozytywny wpis logu dla danego zwiadowcy.

    Args:
        log_entries: Lista wpisów logów.
        scout_id: Hash obiektu zwiadowcy.

    Returns:
        dict[str, Any]: Najnowszy pozytywny wpis lub pusty słownik.
    """

    for entry in reversed(log_entries):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("scout", "")) != scout_id:
            continue
        if _contains_target_signal(entry):
            return entry
    return {}


class DomatowoRunner:
    """Koordynuje analizę, planowanie i wykonanie akcji misji domatowo."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje runnera i jego zależności.

        Args:
            settings: Ustawienia aplikacji.
        """

        self._settings = settings
        self._api = Ag3ntsApiClient(settings)
        self._state = MissionState()
        self.last_output_dir: Path | None = None

    def run(self) -> dict[str, Any]:
        """Wykonuje pełny przebieg rozwiązania zadania.

        Returns:
            dict[str, Any]: Finalna odpowiedź API po akcji `callHelicopter`
            lub informacja o niepowodzeniu.

        Effects:
            Zapisuje artefakty pośrednie do katalogu `output` i drukuje status.
        """

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_dir = self._settings.output_path / timestamp
        self.last_output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        (self._settings.output_path / "latest_run.txt").write_text(
            str(output_dir),
            encoding="utf-8",
        )

        _print_status("Start programu")
        _print_status(f"Katalog output runu: {output_dir}")
        _print_status("Reset planszy (reset)")
        reset_payload = self._api.send_action({"action": "reset"})
        _write_json(output_dir / "step0_reset.json", reset_payload)
        self._state.add_trace("reset", reset_payload)

        _print_status("Ladowanie opisu akcji (help)")
        help_payload = self._api.send_action({"action": "help"})
        _write_json(output_dir / "step1_help.json", help_payload)
        self._state.add_trace("help", help_payload)

        _print_status("Pobieranie cennika akcji (actionCost)")
        action_cost_payload = self._api.send_action({"action": "actionCost"})
        _write_json(output_dir / "step1b_action_cost.json", action_cost_payload)
        self._state.add_trace("actionCost", action_cost_payload)

        _print_status("Pobieranie mapy (getMap)")
        map_payload = self._api.send_action({"action": "getMap"})
        _write_json(output_dir / "step2_map.json", map_payload)
        self._state.add_trace("getMap", map_payload)

        _print_status("Analiza sygnalu i priorytetow")
        intel_payload: dict[str, Any] = {"cells": [], "reason": "Agent Intel wylaczony."}
        if self._settings.enable_intel_agent:
            radio_message = (
                "Przezylem. Bomby zniszczyly miasto. Ukrylem sie w jednym z najwyzszych blokow."
            )
            intel_payload = IntelAgent(self._settings).suggest_cells(map_payload, radio_message)
        _write_json(output_dir / "step3_intel.json", intel_payload)
        self._state.add_trace("intel", intel_payload)

        _print_status("Wyszukiwanie najwyzszych blokow (searchSymbol=B3)")
        search_b3_payload = self._api.send_action({"action": "searchSymbol", "symbol": "B3"})
        _write_json(output_dir / "step3b_search_b3.json", search_b3_payload)
        self._state.add_trace("searchSymbol_B3", search_b3_payload)
        _print_status("Wyszukiwanie szkoly i kosciola (searchSymbol=SZ, KS)")
        search_sz_payload = self._api.send_action({"action": "searchSymbol", "symbol": "SZ"})
        search_ks_payload = self._api.send_action({"action": "searchSymbol", "symbol": "KS"})
        _write_json(output_dir / "step3c_search_sz.json", search_sz_payload)
        _write_json(output_dir / "step3d_search_ks.json", search_ks_payload)
        self._state.add_trace("searchSymbol_SZ", search_sz_payload)
        self._state.add_trace("searchSymbol_KS", search_ks_payload)

        block3_cells_api = _extract_positions_from_search_symbol(search_b3_payload)
        block3_cells_map = _extract_block3_cells_from_map(map_payload)
        block3_cells = list(dict.fromkeys(block3_cells_api + block3_cells_map))
        school_cells = list(
            dict.fromkeys(
                _extract_positions_from_search_symbol(search_sz_payload)
                + _extract_cells_by_tile_from_map(map_payload, "school")
            )
        )
        church_cells = list(
            dict.fromkeys(
                _extract_positions_from_search_symbol(search_ks_payload)
                + _extract_cells_by_tile_from_map(map_payload, "church")
            )
        )

        # Priorytety z IntelAgent pozostają pomocnicze, ale tylko wśród B3.
        intel_cells = [cell for cell in intel_payload.get("cells", []) if cell in block3_cells]
        search_cells = intel_cells + [cell for cell in block3_cells if cell not in intel_cells]

        _print_status("Budowanie planu przeszukania")
        plan_b3 = [cell for cell in search_cells if _CELL_PATTERN.match(cell)]
        plan_sz = [cell for cell in school_cells if _CELL_PATTERN.match(cell)]
        plan_ks = [cell for cell in church_cells if _CELL_PATTERN.match(cell)]
        stage_plans = [
            {"name": "B3", "cells": plan_b3},
            {"name": "SZ", "cells": plan_sz},
            {"name": "KS", "cells": plan_ks},
        ]
        _write_json(
            output_dir / "step4_plan.json",
            {
                "notes": "Plan etapowy: B3, potem SZ, potem KS.",
                "stages": stage_plans,
                "block3_cells_api": block3_cells_api,
                "block3_cells_map": block3_cells_map,
                "school_cells": school_cells,
                "church_cells": church_cells,
            },
        )
        self._state.add_trace(
            "plan",
            {
                "notes": "Plan etapowy: B3, potem SZ, potem KS.",
                "stage_counts": {stage["name"]: len(stage["cells"]) for stage in stage_plans},
            },
        )

        if not any(stage["cells"] for stage in stage_plans):
            _print_status("Brak kandydatow do przeszukania, koncze")
            final_result = {"status": "failed", "reason": "Brak kandydatow do przeszukania."}
            _write_json(output_dir / "final_result.json", final_result)
            return final_result

        _print_status("Tworzenie 2 zwiadowcow (poludnie + polnoc)")
        scout_ids: list[str] = []
        for index in range(1, 3):
            create_payload = self._api.send_action({"action": "create", "type": "scout"})
            scout_id = str(
                create_payload.get("object")
                or create_payload.get("id")
                or f"scout-{index}"
            )
            scout_spawn = str(create_payload.get("spawn", f"A{5 + index}"))
            self._state.units[scout_id] = Unit(
                unit_id=scout_id,
                unit_type="scout",
                position=scout_spawn,
            )
            points_left = _extract_action_points_left(create_payload)
            if points_left is not None:
                self._state.action_points_left = points_left
            self._state.add_trace(f"create_scout_{index}", create_payload)
            scout_ids.append(scout_id)

        _print_status("Start przeszukania: move -> inspect -> getLogs")
        stop_for_low_ap = False
        stage_routes_payload: list[dict[str, Any]] = []
        for stage in stage_plans:
            stage_name = str(stage["name"])
            stage_cells = [cell for cell in stage["cells"] if isinstance(cell, str)]
            if not stage_cells:
                continue
            _print_status(f"Etap {stage_name}: pola={len(stage_cells)}")

            stage_routes: dict[str, list[str]] = {sid: [] for sid in scout_ids}
            if stage_name == "B3":
                north_cells, south_cells = _split_block3_clusters(stage_cells)
                stage_routes[scout_ids[0]] = _order_cells_nearest(
                    self._state.units[scout_ids[0]].position, south_cells
                )
                stage_routes[scout_ids[1]] = _order_cells_nearest(
                    self._state.units[scout_ids[1]].position, north_cells
                )
            else:
                assigned_positions = {
                    sid: self._state.units[sid].position for sid in scout_ids
                }
                for cell in stage_cells:
                    best_sid = min(
                        scout_ids,
                        key=lambda sid: _manhattan_distance(assigned_positions[sid], cell),
                    )
                    stage_routes[best_sid].append(cell)
                    assigned_positions[best_sid] = cell
                for sid in scout_ids:
                    stage_routes[sid] = _order_cells_nearest(
                        self._state.units[sid].position,
                        stage_routes[sid],
                    )

            stage_routes_payload.append({"stage": stage_name, "routes": stage_routes})

            for scout_id in scout_ids:
                cells = stage_routes.get(scout_id, [])
                if not cells:
                    continue
                _print_status(
                    f"Zwiadowca {scout_id[:8]}..., etap={stage_name}, pola={len(cells)}"
                )
                for cell in cells:
                    try:
                        move_payload = self._api.send_action(
                            {
                                "action": "move",
                                "object": scout_id,
                                "where": cell,
                            }
                        )
                    except RuntimeError as exc:
                        error_text = str(exc)
                        self._state.add_trace(
                            "move_error",
                            {"cell": cell, "scout": scout_id, "stage": stage_name, "error": error_text},
                        )
                        if "not enough action points" in error_text.lower() or "koniec punkt" in error_text.lower():
                            _print_status("Koniec punktow akcji podczas ruchu")
                            stop_for_low_ap = True
                            break
                        continue
                    self._state.add_trace(
                        "move",
                        {"cell": cell, "scout": scout_id, "stage": stage_name, "response": move_payload},
                    )
                    self._state.units[scout_id].position = cell
                    points_left = _extract_action_points_left(move_payload)
                    if points_left is not None:
                        self._state.action_points_left = points_left

                    inspect_payload = self._api.send_action({"action": "inspect", "object": scout_id})
                    self._state.add_trace(
                        "inspect",
                        {"cell": cell, "scout": scout_id, "stage": stage_name, "response": inspect_payload},
                    )
                    points_left = _extract_action_points_left(inspect_payload)
                    if points_left is not None:
                        self._state.action_points_left = points_left

                    logs_payload = self._api.send_action({"action": "getLogs"})
                    logs_entries = _extract_logs(logs_payload)
                    last_log = _latest_log_for_scout(logs_entries, scout_id)
                    positive_log = _find_positive_log_for_scout(logs_entries, scout_id)
                    self._state.add_trace(
                        "getLogs",
                        {
                            "cell": cell,
                            "scout": scout_id,
                            "stage": stage_name,
                            "last_log": last_log,
                            "positive_log": positive_log,
                            "logs_count": len(logs_entries),
                        },
                    )

                    detected_field = str(positive_log.get("field", "")).upper()
                    if positive_log and _CELL_PATTERN.match(detected_field):
                        self._state.target_found = True
                        self._state.target_position = detected_field
                        _print_status(f"Cel odnaleziony na polu {self._state.target_position}")
                        break

                    if positive_log and _contains_target_signal(positive_log):
                        self._state.target_found = True
                        self._state.target_position = cell
                        _print_status(f"Cel odnaleziony na polu {self._state.target_position}")
                        break
                if self._state.target_found or stop_for_low_ap:
                    break
            if self._state.target_found or stop_for_low_ap:
                break

        _write_json(output_dir / "step4b_ordered_cells.json", {"stages": stage_routes_payload})
        self._state.add_trace("ordered_cells", {"stages": stage_routes_payload})

        if not self._state.target_found:
            _print_status("Cel nieodnaleziony, zapisuje trace i koncze")
            trace_payload = {"trace": self._state.mission_trace, "state": asdict(self._state)}
            _write_json(output_dir / "step5_mission_trace.json", trace_payload)
            final_result = {
                "status": "failed",
                "reason": "Nie odnaleziono celu w dostepnym budzecie akcji.",
            }
            _write_json(output_dir / "final_result.json", final_result)
            return final_result

        _print_status("Wywolanie ewakuacji (callHelicopter)")
        try:
            helicopter_payload = self._api.send_action(
                {
                    "action": "callHelicopter",
                    "destination": self._state.target_position,
                }
            )
        except RuntimeError as exc:
            error_payload = {
                "status": "failed",
                "reason": "callHelicopter_error",
                "target_position": self._state.target_position,
                "error": str(exc),
            }
            _write_json(output_dir / "step_error_callHelicopter.json", error_payload)
            _write_json(output_dir / "final_result.json", error_payload)
            raise
        self._state.add_trace("callHelicopter", helicopter_payload)
        trace_payload = {"trace": self._state.mission_trace, "state": asdict(self._state)}
        _write_json(output_dir / "step5_mission_trace.json", trace_payload)
        _write_json(output_dir / "final_result.json", helicopter_payload)

        _print_status("Koniec programu")
        return helicopter_payload
