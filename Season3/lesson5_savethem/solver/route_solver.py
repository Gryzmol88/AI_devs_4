"""Solver trasy dla zadania `savethem` oparty o przeszukiwanie grafu stanu."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any

from models.schemas import Position, ProblemData, Solution, TerrainRule, Vehicle


@dataclass(slots=True, frozen=True)
class _NodeState:
    """Reprezentuje stan w grafie przeszukiwania.

    Atrybuty:
        row: Aktualny wiersz.
        col: Aktualna kolumna.
        fuel_left_tenth: Pozostałe paliwo w skali 0.1.
        food_left_tenth: Pozostałe jedzenie w skali 0.1.
        on_foot: Flaga wskazująca, czy agent porusza się pieszo.
    """

    row: int
    col: int
    fuel_left_tenth: int
    food_left_tenth: int
    on_foot: bool


@dataclass(slots=True)
class _PathRecord:
    """Przechowuje koszt i historię ruchów dla stanu.

    Atrybuty:
        total_time: Łączny czas dojścia do stanu.
        moves: Ruchy prowadzące do stanu.
        fuel_used: Zużyte paliwo.
        food_used: Zużyte jedzenie.
    """

    total_time: float
    moves: list[str]
    fuel_used: float
    food_used: float


def solve_route(problem: ProblemData) -> Solution:
    """Wyznacza optymalną trasę zgodną z ograniczeniami zasobów.

    Args:
        problem: Ujednolicone dane zadania.

    Returns:
        Najlepsze znalezione rozwiązanie.

    Raises:
        RuntimeError: Gdy nie znaleziono żadnej poprawnej trasy.
    """

    best_solution: Solution | None = None
    foot_vehicle = _build_foot_vehicle(problem.terrain_rules)

    for vehicle in problem.vehicles:
        candidate = _solve_for_vehicle(problem=problem, start_vehicle=vehicle, foot_vehicle=foot_vehicle)
        if candidate is None:
            continue
        if best_solution is None or _is_better_solution(candidate, best_solution):
            best_solution = candidate

    if best_solution is None:
        raise RuntimeError("Nie znaleziono trasy spełniającej ograniczenia paliwa i jedzenia.")
    return best_solution


def _solve_for_vehicle(problem: ProblemData, start_vehicle: Vehicle, foot_vehicle: Vehicle) -> Solution | None:
    """Szukа najlepszej trasy dla konkretnego pojazdu startowego.

    Args:
        problem: Dane zadania.
        start_vehicle: Pojazd wybrany na starcie.
        foot_vehicle: Parametry ruchu pieszego.

    Returns:
        Rozwiązanie dla wybranego pojazdu lub `None`, jeśli brak trasy.
    """

    start_state = _NodeState(
        row=problem.start.row,
        col=problem.start.col,
        fuel_left_tenth=int(round(problem.fuel_budget * 10)),
        food_left_tenth=int(round(problem.food_budget * 10)),
        on_foot=start_vehicle.name.lower() == "walk",
    )
    queue: list[tuple[float, int, _NodeState]] = [(0.0, 0, start_state)]
    records: dict[_NodeState, _PathRecord] = {
        start_state: _PathRecord(total_time=0.0, moves=[], fuel_used=0.0, food_used=0.0)
    }
    counter = 1
    best_goal_state: _NodeState | None = None

    while queue:
        current_time, _, state = heapq.heappop(queue)
        current_record = records.get(state)
        if current_record is None or current_time > current_record.total_time + 1e-9:
            continue

        if state.row == problem.goal.row and state.col == problem.goal.col:
            if best_goal_state is None:
                best_goal_state = state
            else:
                existing = records[best_goal_state]
                if _is_better_record(current_record, existing):
                    best_goal_state = state
            continue

        active_vehicle = foot_vehicle if state.on_foot else start_vehicle
        for move_name, next_position in _iter_neighbors(Position(state.row, state.col)):
            terrain = _terrain_at(problem.grid, next_position)
            if terrain is None:
                continue
            terrain_rule = problem.terrain_rules.get(
                terrain, TerrainRule(name=terrain, passable_on_foot=True, passable_by_vehicle=True)
            )
            if not _is_passable(terrain=terrain, rule=terrain_rule, vehicle=active_vehicle, on_foot=state.on_foot):
                continue

            fuel_cost_tenth = int(round(active_vehicle.fuel_per_step * 10))
            if not state.on_foot and terrain == "T":
                fuel_cost_tenth += 2
            food_cost_tenth = int(round(active_vehicle.food_per_step * 10))
            if state.fuel_left_tenth < fuel_cost_tenth or state.food_left_tenth < food_cost_tenth:
                continue

            next_state = _NodeState(
                row=next_position.row,
                col=next_position.col,
                fuel_left_tenth=state.fuel_left_tenth - fuel_cost_tenth,
                food_left_tenth=state.food_left_tenth - food_cost_tenth,
                on_foot=state.on_foot,
            )
            next_time = current_record.total_time + (1.0 / max(active_vehicle.speed, 0.1))
            next_record = _PathRecord(
                total_time=next_time,
                moves=[*current_record.moves, move_name],
                fuel_used=current_record.fuel_used + (fuel_cost_tenth / 10.0),
                food_used=current_record.food_used + active_vehicle.food_per_step,
            )
            previous = records.get(next_state)
            if previous is None or _is_better_record(next_record, previous):
                records[next_state] = next_record
                heapq.heappush(queue, (next_record.total_time, counter, next_state))
                counter += 1

        if not state.on_foot:
            switch_state = _NodeState(
                row=state.row,
                col=state.col,
                fuel_left_tenth=state.fuel_left_tenth,
                food_left_tenth=state.food_left_tenth,
                on_foot=True,
            )
            existing_switch = records.get(switch_state)
            if existing_switch is None or _is_better_record(current_record, existing_switch):
                records[switch_state] = _PathRecord(
                    total_time=current_record.total_time,
                    moves=[*current_record.moves, "dismount"],
                    fuel_used=current_record.fuel_used,
                    food_used=current_record.food_used,
                )
                heapq.heappush(queue, (current_record.total_time, counter, switch_state))
                counter += 1

    if best_goal_state is None:
        return None

    goal_record = records[best_goal_state]
    return Solution(
        vehicle_name=start_vehicle.name,
        moves=goal_record.moves,
        total_time=goal_record.total_time,
        fuel_used=goal_record.fuel_used,
        food_used=goal_record.food_used,
    )


def _build_foot_vehicle(terrain_rules: dict[str, TerrainRule]) -> Vehicle:
    """Buduje domyślne parametry ruchu pieszego.

    Args:
        terrain_rules: Zasady terenowe.

    Returns:
        Obiekt pojazdu reprezentujący ruch pieszy.
    """

    allowed = frozenset(name for name, rule in terrain_rules.items() if rule.passable_on_foot)
    return Vehicle(name="on_foot", fuel_per_step=0.0, food_per_step=1.0, speed=1.0, allowed_terrains=allowed)


def _iter_neighbors(position: Position) -> list[tuple[str, Position]]:
    """Zwraca sąsiadów pozycji z nazwami ruchów.

    Args:
        position: Bieżąca pozycja.

    Returns:
        Lista par `(nazwa_ruchu, pozycja_docelowa)`.
    """

    return [
        ("up", Position(position.row - 1, position.col)),
        ("down", Position(position.row + 1, position.col)),
        ("left", Position(position.row, position.col - 1)),
        ("right", Position(position.row, position.col + 1)),
    ]


def _terrain_at(grid: list[list[str]], position: Position) -> str | None:
    """Pobiera symbol terenu z mapy dla wskazanej pozycji.

    Args:
        grid: Siatka mapy.
        position: Pozycja do odczytu.

    Returns:
        Symbol terenu lub `None` dla wyjścia poza mapę.
    """

    if position.row < 0 or position.col < 0:
        return None
    if position.row >= len(grid) or position.col >= len(grid[position.row]):
        return None
    return str(grid[position.row][position.col])


def _is_passable(terrain: str, rule: TerrainRule, vehicle: Vehicle, on_foot: bool) -> bool:
    """Sprawdza, czy można wejść na pole danym środkiem transportu.

    Args:
        terrain: Typ terenu na polu docelowym.
        rule: Reguła terenu.
        vehicle: Aktualnie używany środek transportu.
        on_foot: Flaga trybu pieszego.

    Returns:
        `True`, gdy ruch jest dozwolony.
    """

    if on_foot:
        return rule.passable_on_foot and terrain in vehicle.allowed_terrains
    return rule.passable_by_vehicle and terrain in vehicle.allowed_terrains


def _is_better_record(candidate: _PathRecord, current: _PathRecord) -> bool:
    """Porównuje dwie ścieżki dla tego samego stanu.

    Args:
        candidate: Nowa ścieżka.
        current: Aktualnie najlepsza ścieżka.

    Returns:
        `True`, gdy kandydat jest lepszy.
    """

    if candidate.total_time < current.total_time - 1e-9:
        return True
    if abs(candidate.total_time - current.total_time) <= 1e-9:
        if candidate.food_used < current.food_used - 1e-9:
            return True
        if abs(candidate.food_used - current.food_used) <= 1e-9:
            return candidate.fuel_used < current.fuel_used - 1e-9
    return False


def _is_better_solution(candidate: Solution, current: Solution) -> bool:
    """Porównuje dwa rozwiązania końcowe.

    Args:
        candidate: Kandydat na nowe najlepsze rozwiązanie.
        current: Aktualnie najlepsze rozwiązanie.

    Returns:
        `True`, gdy kandydat jest lepszy według funkcji celu.
    """

    if candidate.total_time < current.total_time - 1e-9:
        return True
    if abs(candidate.total_time - current.total_time) <= 1e-9:
        if candidate.food_used < current.food_used - 1e-9:
            return True
        if abs(candidate.food_used - current.food_used) <= 1e-9:
            return candidate.fuel_used < current.fuel_used - 1e-9
    return False


def solution_to_dict(solution: Solution) -> dict[str, Any]:
    """Konwertuje rozwiązanie do słownika JSON-owalnego.

    Args:
        solution: Rozwiązanie zwrócone przez solver.

    Returns:
        Słownik gotowy do zapisu w pliku wynikowym.
    """

    return {
        "vehicle_name": solution.vehicle_name,
        "moves": solution.moves,
        "total_time": solution.total_time,
        "fuel_used": solution.fuel_used,
        "food_used": solution.food_used,
        "verify_answer": solution.to_verify_answer(),
    }
