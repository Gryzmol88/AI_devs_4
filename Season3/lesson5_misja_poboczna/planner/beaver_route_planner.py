"""Planner tras dla misji pobocznej z heurystyką "tam są bobry"."""

from __future__ import annotations

from dataclasses import dataclass
import heapq
from typing import Any

from models import Position, RouteCandidate, VehicleSpec, WorldState


@dataclass(slots=True, frozen=True)
class _SearchState:
    """Opisuje stan przeszukiwania.

    Atrybuty:
        row: Wiersz pozycji.
        col: Kolumna pozycji.
        fuel_left_tenth: Pozostałe paliwo (x10).
        food_left_tenth: Pozostałe jedzenie (x10).
        mode: Aktualny tryb ruchu (`vehicle` lub `walk`).
        dismounted: Czy wykonano już `dismount`.
    """

    row: int
    col: int
    fuel_left_tenth: int
    food_left_tenth: int
    mode: str
    dismounted: bool


@dataclass(slots=True)
class _PathData:
    """Trzyma dane ścieżki dla stanu.

    Atrybuty:
        objective: Koszt celu optymalizacji.
        moves: Lista komend.
        water_adjacent_steps: Kroki sąsiadujące z wodą.
        north_score: Suma premii za północ mapy.
        water_steps: Liczba kroków po wodzie.
    """

    objective: float
    moves: list[str]
    water_adjacent_steps: int
    north_score: int
    water_steps: int


@dataclass(slots=True, frozen=True)
class Strategy:
    """Definiuje strategię planowania trasy.

    Atrybuty:
        name: Nazwa strategii.
        time_weight: Waga czasu ruchu.
        water_adjacency_weight: Premia za bliskość wody.
        north_weight: Premia za północne pozycje.
        water_step_weight: Premia za kroki po wodzie.
    """

    name: str
    time_weight: float
    water_adjacency_weight: float
    north_weight: float
    water_step_weight: float


class BeaverRoutePlanner:
    """Wyznacza kandydackie trasy bazujące na wskazówce o bobrach."""

    def generate_candidates(self, world: WorldState) -> list[RouteCandidate]:
        """Buduje zestaw kandydatów do testów `/verify`.

        Args:
            world: Znormalizowany stan świata.

        Returns:
            Lista kandydatów trasy.
        """

        strategies = [
            Strategy("fastest", 1.0, 0.0, 0.0, 0.0),
            Strategy("beaver_north", 1.0, 0.9, 0.8, 0.4),
            Strategy("waterline", 1.0, 1.4, 0.3, 0.8),
            Strategy("north_bias", 1.0, 0.2, 1.2, 0.0),
        ]

        vehicles_in_order = self._vehicle_priority(world.vehicles)
        candidates: list[RouteCandidate] = []
        for strategy in strategies:
            for vehicle_name in vehicles_in_order:
                route = self._search_route(world=world, vehicle_name=vehicle_name, strategy=strategy)
                if route is not None:
                    candidates.append(route)

        unique: list[RouteCandidate] = []
        seen_answers: set[tuple[str, ...]] = set()
        for candidate in sorted(candidates, key=lambda x: x.score, reverse=True):
            answer_key = tuple(candidate.to_answer())
            if answer_key in seen_answers:
                continue
            seen_answers.add(answer_key)
            unique.append(candidate)
        return unique

    def generate_river_patrol_candidates(self, world: WorldState, max_steps: int = 14) -> list[RouteCandidate]:
        """Buduje trasy patrolowe skupione na dojściu do rzeki i ruchu wzdłuż wody.

        Args:
            world: Znormalizowany stan świata.
            max_steps: Maksymalna długość sekwencji komend.

        Returns:
            Lista kandydatów tras patrolowych.
        """

        strategies = [
            Strategy("river_patrol", 0.2, 2.2, 0.9, 0.7),
            Strategy("north_river_patrol", 0.2, 1.8, 1.5, 0.5),
        ]
        vehicles_in_order = self._vehicle_priority(world.vehicles)
        candidates: list[RouteCandidate] = []
        for vehicle_name in vehicles_in_order:
            for strategy in strategies:
                route = self._beam_patrol(world=world, vehicle_name=vehicle_name, strategy=strategy, max_steps=max_steps)
                if route is not None:
                    candidates.append(route)

        unique: list[RouteCandidate] = []
        seen_answers: set[tuple[str, ...]] = set()
        for candidate in sorted(candidates, key=lambda x: x.score, reverse=True):
            key = tuple(candidate.to_answer())
            if key in seen_answers:
                continue
            seen_answers.add(key)
            unique.append(candidate)
        return unique

    def generate_water_contact_candidates(self, world: WorldState) -> list[RouteCandidate]:
        """Buduje krótkie trasy prowadzące do kontaktu z wodą.

        Kontakt z wodą oznacza:
        - wejście na kafelek `W` (jeśli tryb ruchu pozwala),
        - albo wejście na kafelek sąsiadujący z `W`.

        Args:
            world: Znormalizowany stan świata.

        Returns:
            Lista kandydatów posortowana od najbardziej oszczędnych.
        """

        candidates: list[RouteCandidate] = []
        for vehicle_name in self._vehicle_priority(world.vehicles):
            candidate = self._search_water_contact(world=world, vehicle_name=vehicle_name)
            if candidate is not None:
                candidates.append(candidate)

        candidates.sort(
            key=lambda item: (
                len(item.commands),
                float(item.metrics.get("food_used", 9999.0)),
                float(item.metrics.get("fuel_used", 9999.0)),
                -int(item.metrics.get("north_score", 0)),
            )
        )
        return candidates

    def generate_failure_exploration_candidates(
        self,
        world: WorldState,
        max_routes: int = 20,
    ) -> list[RouteCandidate]:
        """Generuje trasy eksploracyjne wokół `W` i `T`, bez dochodzenia do `G`.

        Trasy mają zwiększać pokrycie obszaru wodno-leśnego i celowo nie kończyć
        zadania głównego (nie prowadzą na `G`).

        Args:
            world: Znormalizowany stan świata.
            max_routes: Maksymalna liczba tras do wygenerowania.

        Returns:
            Lista kandydatów tras eksploracyjnych.
        """

        targets = self._collect_exploration_targets(world)
        candidates: list[RouteCandidate] = []

        for vehicle_name in self._vehicle_priority(world.vehicles):
            for target in targets:
                base = self._shortest_path_to_target(
                    world=world,
                    vehicle_name=vehicle_name,
                    target=target,
                    avoid_goal=True,
                )
                if base is None:
                    continue
                base_commands, fuel_used, food_used = base
                if not base_commands:
                    continue
                variants = self._build_local_exploration_variants(
                    world=world,
                    vehicle_name=vehicle_name,
                    prefix=base_commands,
                    max_variants=3,
                )
                for index, commands in enumerate(variants):
                    if _touches_goal(world, commands):
                        continue
                    metrics = _estimate_metrics(world=world, vehicle_name=vehicle_name, commands=commands)
                    if metrics is None:
                        continue
                    candidate = RouteCandidate(
                        name=f"failure_explore_{vehicle_name}_{target.row}_{target.col}_{index}",
                        vehicle_name=vehicle_name,
                        commands=commands,
                        score=float(metrics["water_tree_coverage"]) - float(metrics["length"]) / 100.0,
                        metrics=metrics,
                    )
                    candidates.append(candidate)
                    if len(candidates) >= max_routes:
                        break
                if len(candidates) >= max_routes:
                    break
            if len(candidates) >= max_routes:
                break

        candidates.sort(
            key=lambda item: (
                -int(item.metrics.get("water_tree_coverage", 0)),
                -int(item.metrics.get("north_score", 0)),
                int(item.metrics.get("length", 999)),
                float(item.metrics.get("food_used", 999.0)),
            )
        )
        unique: list[RouteCandidate] = []
        seen: set[tuple[str, ...]] = set()
        for candidate in candidates:
            key = tuple(candidate.to_answer())
            if key in seen:
                continue
            seen.add(key)
            unique.append(candidate)
        return unique[:max_routes]

    def _vehicle_priority(self, vehicles: dict[str, VehicleSpec]) -> list[str]:
        """Zwraca priorytet testowania pojazdów.

        Args:
            vehicles: Słownik pojazdów.

        Returns:
            Lista nazw pojazdów w kolejności testowej.
        """

        priority = ["rocket", "horse", "car", "walk"]
        return [name for name in priority if name in vehicles]

    def _search_route(self, world: WorldState, vehicle_name: str, strategy: Strategy) -> RouteCandidate | None:
        """Przeszukuje przestrzeń stanów i buduje trasę dla strategii.

        Args:
            world: Dane świata.
            vehicle_name: Nazwa pojazdu startowego.
            strategy: Strategia optymalizacji.

        Returns:
            Kandydat trasy lub `None`, jeśli brak trasy.
        """

        start_mode = "walk" if vehicle_name == "walk" else "vehicle"
        start_state = _SearchState(
            row=world.start.row,
            col=world.start.col,
            fuel_left_tenth=int(round(world.fuel_budget * 10)),
            food_left_tenth=int(round(world.food_budget * 10)),
            mode=start_mode,
            dismounted=start_mode == "walk",
        )

        queue: list[tuple[float, int, _SearchState]] = []
        counter = 0
        heapq.heappush(queue, (0.0, counter, start_state))
        records: dict[_SearchState, _PathData] = {
            start_state: _PathData(objective=0.0, moves=[], water_adjacent_steps=0, north_score=0, water_steps=0)
        }
        best_goal: tuple[_SearchState, _PathData] | None = None

        while queue:
            current_objective, _, state = heapq.heappop(queue)
            data = records.get(state)
            if data is None:
                continue
            if current_objective > data.objective + 1e-9:
                continue

            if state.row == world.goal.row and state.col == world.goal.col:
                if best_goal is None or data.objective < best_goal[1].objective:
                    best_goal = (state, data)
                continue

            mode_vehicle = world.vehicles["walk"] if state.mode == "walk" else world.vehicles[vehicle_name]
            for move_name, next_pos in _neighbors(Position(state.row, state.col)):
                if not _inside(world.grid, next_pos):
                    continue
                tile = world.grid[next_pos.row][next_pos.col]
                if not self._can_enter(tile=tile, mode=state.mode, vehicle_name=vehicle_name):
                    continue

                fuel_cost = mode_vehicle.fuel_per_step
                if state.mode == "vehicle" and tile == "T":
                    fuel_cost += 0.2
                food_cost = mode_vehicle.food_per_step

                fuel_left = state.fuel_left_tenth - int(round(fuel_cost * 10))
                food_left = state.food_left_tenth - int(round(food_cost * 10))
                if fuel_left < 0 or food_left < 0:
                    continue

                water_adjacent_bonus = 1 if _is_adjacent_to_water(world.grid, next_pos) else 0
                north_bonus = max(0, len(world.grid) - 1 - next_pos.row)
                water_step_bonus = 1 if tile == "W" else 0

                step_cost = (
                    strategy.time_weight * (1.0 / max(mode_vehicle.speed, 0.1))
                    - strategy.water_adjacency_weight * water_adjacent_bonus
                    - strategy.north_weight * (north_bonus / 10.0)
                    - strategy.water_step_weight * water_step_bonus
                )

                next_state = _SearchState(
                    row=next_pos.row,
                    col=next_pos.col,
                    fuel_left_tenth=fuel_left,
                    food_left_tenth=food_left,
                    mode=state.mode,
                    dismounted=state.dismounted,
                )
                next_data = _PathData(
                    objective=data.objective + step_cost,
                    moves=[*data.moves, move_name],
                    water_adjacent_steps=data.water_adjacent_steps + water_adjacent_bonus,
                    north_score=data.north_score + north_bonus,
                    water_steps=data.water_steps + water_step_bonus,
                )
                if _is_better(next_data, records.get(next_state)):
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

            if state.mode == "vehicle" and not state.dismounted:
                next_state = _SearchState(
                    row=state.row,
                    col=state.col,
                    fuel_left_tenth=state.fuel_left_tenth,
                    food_left_tenth=state.food_left_tenth,
                    mode="walk",
                    dismounted=True,
                )
                next_data = _PathData(
                    objective=data.objective,
                    moves=[*data.moves, "dismount"],
                    water_adjacent_steps=data.water_adjacent_steps,
                    north_score=data.north_score,
                    water_steps=data.water_steps,
                )
                if _is_better(next_data, records.get(next_state)):
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

        if best_goal is None:
            return None

        _, best_data = best_goal
        score = -best_data.objective
        return RouteCandidate(
            name=f"{strategy.name}_{vehicle_name}",
            vehicle_name=vehicle_name,
            commands=best_data.moves,
            score=score,
            metrics={
                "water_adjacent_steps": best_data.water_adjacent_steps,
                "north_score": best_data.north_score,
                "water_steps": best_data.water_steps,
                "objective": best_data.objective,
            },
        )

    def _can_enter(self, tile: str, mode: str, vehicle_name: str) -> bool:
        """Sprawdza, czy dany tryb może wejść na kafelek.

        Args:
            tile: Symbol kafelka.
            mode: Aktualny tryb (`vehicle` lub `walk`).
            vehicle_name: Nazwa pojazdu startowego.

        Returns:
            `True`, jeśli wejście jest dozwolone.
        """

        if tile == "R" or tile == "#":
            return False
        if tile == "W":
            if mode == "walk":
                return True
            return vehicle_name == "horse"
        return True

    def _beam_patrol(
        self,
        world: WorldState,
        vehicle_name: str,
        strategy: Strategy,
        max_steps: int,
    ) -> RouteCandidate | None:
        """Generuje trasę patrolową metodą beam-search.

        Args:
            world: Dane świata.
            vehicle_name: Pojazd startowy.
            strategy: Strategia oceny ścieżki.
            max_steps: Limit długości komend.

        Returns:
            Kandydat trasy lub `None`.
        """

        beam_width = 80
        start_mode = "walk" if vehicle_name == "walk" else "vehicle"
        start = _SearchState(
            row=world.start.row,
            col=world.start.col,
            fuel_left_tenth=int(round(world.fuel_budget * 10)),
            food_left_tenth=int(round(world.food_budget * 10)),
            mode=start_mode,
            dismounted=start_mode == "walk",
        )
        start_data = _PathData(objective=0.0, moves=[], water_adjacent_steps=0, north_score=0, water_steps=0)
        frontier: list[tuple[_SearchState, _PathData]] = [(start, start_data)]
        best_route: RouteCandidate | None = None

        for _ in range(max_steps):
            next_frontier: list[tuple[_SearchState, _PathData]] = []
            for state, data in frontier:
                mode_vehicle = world.vehicles["walk"] if state.mode == "walk" else world.vehicles[vehicle_name]
                for move_name, next_pos in _neighbors(Position(state.row, state.col)):
                    if not _inside(world.grid, next_pos):
                        continue
                    tile = world.grid[next_pos.row][next_pos.col]
                    if not self._can_enter(tile=tile, mode=state.mode, vehicle_name=vehicle_name):
                        continue

                    fuel_cost = mode_vehicle.fuel_per_step + (0.2 if state.mode == "vehicle" and tile == "T" else 0.0)
                    food_cost = mode_vehicle.food_per_step
                    fuel_left = state.fuel_left_tenth - int(round(fuel_cost * 10))
                    food_left = state.food_left_tenth - int(round(food_cost * 10))
                    if fuel_left < 0 or food_left < 0:
                        continue

                    water_adjacent_bonus = 1 if _is_adjacent_to_water(world.grid, next_pos) else 0
                    north_bonus = max(0, len(world.grid) - 1 - next_pos.row)
                    water_step_bonus = 1 if tile == "W" else 0
                    goal_penalty = 12.0 if (next_pos.row == world.goal.row and next_pos.col == world.goal.col) else 0.0

                    step_cost = (
                        strategy.time_weight * (1.0 / max(mode_vehicle.speed, 0.1))
                        - strategy.water_adjacency_weight * water_adjacent_bonus
                        - strategy.north_weight * (north_bonus / 10.0)
                        - strategy.water_step_weight * water_step_bonus
                        + goal_penalty
                    )

                    next_state = _SearchState(
                        row=next_pos.row,
                        col=next_pos.col,
                        fuel_left_tenth=fuel_left,
                        food_left_tenth=food_left,
                        mode=state.mode,
                        dismounted=state.dismounted,
                    )
                    next_data = _PathData(
                        objective=data.objective + step_cost,
                        moves=[*data.moves, move_name],
                        water_adjacent_steps=data.water_adjacent_steps + water_adjacent_bonus,
                        north_score=data.north_score + north_bonus,
                        water_steps=data.water_steps + water_step_bonus,
                    )
                    next_frontier.append((next_state, next_data))

                if state.mode == "vehicle" and not state.dismounted:
                    next_state = _SearchState(
                        row=state.row,
                        col=state.col,
                        fuel_left_tenth=state.fuel_left_tenth,
                        food_left_tenth=state.food_left_tenth,
                        mode="walk",
                        dismounted=True,
                    )
                    next_data = _PathData(
                        objective=data.objective - 0.1,
                        moves=[*data.moves, "dismount"],
                        water_adjacent_steps=data.water_adjacent_steps,
                        north_score=data.north_score,
                        water_steps=data.water_steps,
                    )
                    next_frontier.append((next_state, next_data))

            if not next_frontier:
                break

            next_frontier.sort(
                key=lambda item: (
                    item[1].objective,
                    -item[1].water_adjacent_steps,
                    -item[1].water_steps,
                    -item[1].north_score,
                )
            )
            frontier = next_frontier[:beam_width]

            state, data = frontier[0]
            if not (state.row == world.goal.row and state.col == world.goal.col):
                best_route = RouteCandidate(
                    name=f"{strategy.name}_{vehicle_name}",
                    vehicle_name=vehicle_name,
                    commands=data.moves,
                    score=-data.objective,
                    metrics={
                        "water_adjacent_steps": data.water_adjacent_steps,
                        "water_steps": data.water_steps,
                        "north_score": data.north_score,
                        "fuel_left": state.fuel_left_tenth / 10.0,
                        "food_left": state.food_left_tenth / 10.0,
                    },
                )

        return best_route

    def _search_water_contact(self, world: WorldState, vehicle_name: str) -> RouteCandidate | None:
        """Szuka najtańszej trasy do pierwszego kontaktu z wodą.

        Args:
            world: Dane świata.
            vehicle_name: Nazwa pojazdu startowego.

        Returns:
            Kandydat trasy lub `None`, jeśli nie ma legalnej drogi.
        """

        start_mode = "walk" if vehicle_name == "walk" else "vehicle"
        start_state = _SearchState(
            row=world.start.row,
            col=world.start.col,
            fuel_left_tenth=int(round(world.fuel_budget * 10)),
            food_left_tenth=int(round(world.food_budget * 10)),
            mode=start_mode,
            dismounted=start_mode == "walk",
        )
        queue: list[tuple[float, int, _SearchState]] = []
        counter = 0
        heapq.heappush(queue, (0.0, counter, start_state))
        records: dict[_SearchState, _PathData] = {
            start_state: _PathData(objective=0.0, moves=[], water_adjacent_steps=0, north_score=0, water_steps=0)
        }
        visited_best: dict[tuple[int, int, str, bool], float] = {}

        while queue:
            current_cost, _, state = heapq.heappop(queue)
            data = records.get(state)
            if data is None or current_cost > data.objective + 1e-9:
                continue

            tile = world.grid[state.row][state.col]
            in_contact = tile == "W" or _is_adjacent_to_water(world.grid, Position(state.row, state.col))
            if in_contact and data.moves:
                food_used = (world.food_budget * 10 - state.food_left_tenth) / 10.0
                fuel_used = (world.fuel_budget * 10 - state.fuel_left_tenth) / 10.0
                return RouteCandidate(
                    name=f"water_contact_{vehicle_name}",
                    vehicle_name=vehicle_name,
                    commands=data.moves,
                    score=-(data.objective),
                    metrics={
                        "food_used": food_used,
                        "fuel_used": fuel_used,
                        "north_score": data.north_score,
                        "water_steps": data.water_steps,
                        "water_adjacent_steps": data.water_adjacent_steps,
                    },
                )

            key = (state.row, state.col, state.mode, state.dismounted)
            best_for_key = visited_best.get(key)
            if best_for_key is not None and data.objective >= best_for_key - 1e-9:
                continue
            visited_best[key] = data.objective

            mode_vehicle = world.vehicles["walk"] if state.mode == "walk" else world.vehicles[vehicle_name]
            for move_name, next_pos in _neighbors(Position(state.row, state.col)):
                if not _inside(world.grid, next_pos):
                    continue
                next_tile = world.grid[next_pos.row][next_pos.col]
                if not self._can_enter(tile=next_tile, mode=state.mode, vehicle_name=vehicle_name):
                    continue

                fuel_cost = mode_vehicle.fuel_per_step + (0.2 if state.mode == "vehicle" and next_tile == "T" else 0.0)
                food_cost = mode_vehicle.food_per_step
                fuel_left = state.fuel_left_tenth - int(round(fuel_cost * 10))
                food_left = state.food_left_tenth - int(round(food_cost * 10))
                if fuel_left < 0 or food_left < 0:
                    continue

                water_adjacent = 1 if _is_adjacent_to_water(world.grid, next_pos) else 0
                water_step = 1 if next_tile == "W" else 0
                north_bonus = max(0, len(world.grid) - 1 - next_pos.row)

                step_cost = food_cost * 3.0 + fuel_cost * 1.5 - water_adjacent * 0.8 - water_step * 1.2 - (north_bonus / 20.0)
                next_state = _SearchState(
                    row=next_pos.row,
                    col=next_pos.col,
                    fuel_left_tenth=fuel_left,
                    food_left_tenth=food_left,
                    mode=state.mode,
                    dismounted=state.dismounted,
                )
                next_data = _PathData(
                    objective=data.objective + step_cost,
                    moves=[*data.moves, move_name],
                    water_adjacent_steps=data.water_adjacent_steps + water_adjacent,
                    north_score=data.north_score + north_bonus,
                    water_steps=data.water_steps + water_step,
                )
                prev = records.get(next_state)
                if prev is None or next_data.objective < prev.objective - 1e-9:
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

            if state.mode == "vehicle" and not state.dismounted:
                next_state = _SearchState(
                    row=state.row,
                    col=state.col,
                    fuel_left_tenth=state.fuel_left_tenth,
                    food_left_tenth=state.food_left_tenth,
                    mode="walk",
                    dismounted=True,
                )
                next_data = _PathData(
                    objective=data.objective + 0.05,
                    moves=[*data.moves, "dismount"],
                    water_adjacent_steps=data.water_adjacent_steps,
                    north_score=data.north_score,
                    water_steps=data.water_steps,
                )
                prev = records.get(next_state)
                if prev is None or next_data.objective < prev.objective - 1e-9:
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

        return None

    def _collect_exploration_targets(self, world: WorldState) -> list[Position]:
        """Buduje listę pól docelowych dla eksploracji wokół wody i drzew.

        Args:
            world: Dane świata.

        Returns:
            Lista pozycji uporządkowana od najbardziej „beaver-friendly”.
        """

        targets: list[tuple[int, Position]] = []
        for row_index, row in enumerate(world.grid):
            for col_index, tile in enumerate(row):
                pos = Position(row=row_index, col=col_index)
                if row_index == world.goal.row and col_index == world.goal.col:
                    continue
                near_water = _is_adjacent_to_water(world.grid, pos)
                near_tree = _is_adjacent_to_tree(world.grid, pos)
                if tile in {"W", "T"} or near_water or near_tree:
                    north_bonus = max(0, len(world.grid) - 1 - row_index)
                    weight = (
                        (20 if tile == "W" else 0)
                        + (12 if tile == "T" else 0)
                        + (8 if near_water else 0)
                        + (4 if near_tree else 0)
                        + north_bonus
                    )
                    targets.append((weight, pos))
        targets.sort(key=lambda item: item[0], reverse=True)
        return [pos for _, pos in targets]

    def _shortest_path_to_target(
        self,
        world: WorldState,
        vehicle_name: str,
        target: Position,
        avoid_goal: bool,
    ) -> tuple[list[str], float, float] | None:
        """Znajduje najkrótszą trasę do wskazanego pola przy zachowaniu ograniczeń.

        Args:
            world: Dane świata.
            vehicle_name: Nazwa pojazdu startowego.
            target: Pole docelowe.
            avoid_goal: Czy unikać wejścia na `G`.

        Returns:
            Krotka `(commands, fuel_used, food_used)` lub `None`.
        """

        start_mode = "walk" if vehicle_name == "walk" else "vehicle"
        start_state = _SearchState(
            row=world.start.row,
            col=world.start.col,
            fuel_left_tenth=int(round(world.fuel_budget * 10)),
            food_left_tenth=int(round(world.food_budget * 10)),
            mode=start_mode,
            dismounted=start_mode == "walk",
        )
        queue: list[tuple[float, int, _SearchState]] = []
        counter = 0
        heapq.heappush(queue, (0.0, counter, start_state))
        records: dict[_SearchState, _PathData] = {
            start_state: _PathData(objective=0.0, moves=[], water_adjacent_steps=0, north_score=0, water_steps=0)
        }
        visited: set[tuple[int, int, int, int, str, bool]] = set()

        while queue:
            _, _, state = heapq.heappop(queue)
            data = records.get(state)
            if data is None:
                continue
            state_key = (
                state.row,
                state.col,
                state.fuel_left_tenth,
                state.food_left_tenth,
                state.mode,
                state.dismounted,
            )
            if state_key in visited:
                continue
            visited.add(state_key)

            if state.row == target.row and state.col == target.col:
                fuel_used = (world.fuel_budget * 10 - state.fuel_left_tenth) / 10.0
                food_used = (world.food_budget * 10 - state.food_left_tenth) / 10.0
                return data.moves, fuel_used, food_used

            mode_vehicle = world.vehicles["walk"] if state.mode == "walk" else world.vehicles[vehicle_name]
            for move_name, next_pos in _neighbors(Position(state.row, state.col)):
                if not _inside(world.grid, next_pos):
                    continue
                if avoid_goal and next_pos.row == world.goal.row and next_pos.col == world.goal.col:
                    continue
                tile = world.grid[next_pos.row][next_pos.col]
                if not self._can_enter(tile=tile, mode=state.mode, vehicle_name=vehicle_name):
                    continue
                fuel_cost = mode_vehicle.fuel_per_step + (0.2 if state.mode == "vehicle" and tile == "T" else 0.0)
                food_cost = mode_vehicle.food_per_step
                fuel_left = state.fuel_left_tenth - int(round(fuel_cost * 10))
                food_left = state.food_left_tenth - int(round(food_cost * 10))
                if fuel_left < 0 or food_left < 0:
                    continue
                next_state = _SearchState(
                    row=next_pos.row,
                    col=next_pos.col,
                    fuel_left_tenth=fuel_left,
                    food_left_tenth=food_left,
                    mode=state.mode,
                    dismounted=state.dismounted,
                )
                next_data = _PathData(
                    objective=data.objective + 1.0,
                    moves=[*data.moves, move_name],
                    water_adjacent_steps=data.water_adjacent_steps + (1 if _is_adjacent_to_water(world.grid, next_pos) else 0),
                    north_score=data.north_score + max(0, len(world.grid) - 1 - next_pos.row),
                    water_steps=data.water_steps + (1 if tile == "W" else 0),
                )
                prev = records.get(next_state)
                if prev is None or next_data.objective < prev.objective - 1e-9:
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

            if state.mode == "vehicle" and not state.dismounted:
                next_state = _SearchState(
                    row=state.row,
                    col=state.col,
                    fuel_left_tenth=state.fuel_left_tenth,
                    food_left_tenth=state.food_left_tenth,
                    mode="walk",
                    dismounted=True,
                )
                next_data = _PathData(
                    objective=data.objective + 0.1,
                    moves=[*data.moves, "dismount"],
                    water_adjacent_steps=data.water_adjacent_steps,
                    north_score=data.north_score,
                    water_steps=data.water_steps,
                )
                prev = records.get(next_state)
                if prev is None or next_data.objective < prev.objective - 1e-9:
                    records[next_state] = next_data
                    counter += 1
                    heapq.heappush(queue, (next_data.objective, counter, next_state))

        return None

    def _build_local_exploration_variants(
        self,
        world: WorldState,
        vehicle_name: str,
        prefix: list[str],
        max_variants: int,
    ) -> list[list[str]]:
        """Buduje warianty krótkiej eksploracji po dotarciu do strefy celu.

        Args:
            world: Dane świata.
            vehicle_name: Nazwa pojazdu.
            prefix: Ścieżka dojścia.
            max_variants: Liczba wariantów.

        Returns:
            Lista wariantów komend.
        """

        patterns = [
            ["left", "right", "up", "down"],
            ["up", "right", "down", "left"],
            ["right", "right", "left", "left"],
            ["up", "up", "down", "down"],
            ["dismount", "up", "right", "left"],
        ]
        variants: list[list[str]] = []
        for pattern in patterns:
            commands = [*prefix, *pattern]
            if _estimate_metrics(world=world, vehicle_name=vehicle_name, commands=commands) is None:
                continue
            variants.append(commands)
            if len(variants) >= max_variants:
                break
        if not variants:
            variants.append(prefix)
        return variants


def _neighbors(position: Position) -> list[tuple[str, Position]]:
    """Zwraca sąsiadów pozycji w czterech kierunkach.

    Args:
        position: Aktualna pozycja.

    Returns:
        Lista par `(komenda, pozycja_docelowa)`.
    """

    return [
        ("up", Position(position.row - 1, position.col)),
        ("down", Position(position.row + 1, position.col)),
        ("left", Position(position.row, position.col - 1)),
        ("right", Position(position.row, position.col + 1)),
    ]


def _inside(grid: list[list[str]], position: Position) -> bool:
    """Sprawdza, czy pozycja mieści się w granicach mapy.

    Args:
        grid: Mapa.
        position: Pozycja.

    Returns:
        `True`, gdy pozycja jest w granicach mapy.
    """

    return 0 <= position.row < len(grid) and 0 <= position.col < len(grid[0])


def _is_adjacent_to_water(grid: list[list[str]], position: Position) -> bool:
    """Sprawdza, czy pozycja sąsiaduje z kafelkiem `W`.

    Args:
        grid: Mapa.
        position: Pozycja.

    Returns:
        `True`, gdy co najmniej jeden sąsiad to `W`.
    """

    for _, neighbor in _neighbors(position):
        if not _inside(grid, neighbor):
            continue
        if grid[neighbor.row][neighbor.col] == "W":
            return True
    return False


def _is_adjacent_to_tree(grid: list[list[str]], position: Position) -> bool:
    """Sprawdza, czy pozycja sąsiaduje z kafelkiem `T`.

    Args:
        grid: Mapa.
        position: Pozycja.

    Returns:
        `True`, gdy co najmniej jeden sąsiad to `T`.
    """

    for _, neighbor in _neighbors(position):
        if not _inside(grid, neighbor):
            continue
        if grid[neighbor.row][neighbor.col] == "T":
            return True
    return False


def _is_better(candidate: _PathData, current: _PathData | None) -> bool:
    """Porównuje dwa rekordy ścieżek.

    Args:
        candidate: Kandydat nowej ścieżki.
        current: Aktualny rekord.

    Returns:
        `True`, gdy kandydat jest lepszy.
    """

    if current is None:
        return True
    return candidate.objective < current.objective - 1e-9


def _estimate_metrics(world: WorldState, vehicle_name: str, commands: list[str]) -> dict[str, Any] | None:
    """Szacuje metryki i zużycie zasobów dla sekwencji komend.

    Args:
        world: Dane świata.
        vehicle_name: Nazwa startowego pojazdu.
        commands: Sekwencja komend.

    Returns:
        Słownik metryk lub `None`, jeśli komendy są niepoprawne.
    """

    row = world.start.row
    col = world.start.col
    mode = "walk" if vehicle_name == "walk" else "vehicle"
    dismounted = mode == "walk"
    fuel_left = world.fuel_budget
    food_left = world.food_budget
    water_tree_coverage = 0
    north_score = 0
    visited_cells: set[tuple[int, int]] = {(row, col)}

    for command in commands:
        if command == "dismount":
            if mode == "walk" or dismounted:
                return None
            mode = "walk"
            dismounted = True
            continue

        delta = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }.get(command)
        if delta is None:
            return None
        next_row = row + delta[0]
        next_col = col + delta[1]
        if next_row < 0 or next_col < 0 or next_row >= len(world.grid) or next_col >= len(world.grid[0]):
            return None
        tile = world.grid[next_row][next_col]
        if tile in {"R", "#"}:
            return None
        if tile == "W" and mode == "vehicle" and vehicle_name != "horse":
            return None

        active = world.vehicles["walk"] if mode == "walk" else world.vehicles[vehicle_name]
        fuel_cost = active.fuel_per_step + (0.2 if mode == "vehicle" and tile == "T" else 0.0)
        food_cost = active.food_per_step
        fuel_left -= fuel_cost
        food_left -= food_cost
        if fuel_left < -1e-9 or food_left < -1e-9:
            return None

        row, col = next_row, next_col
        visited_cells.add((row, col))
        if tile in {"W", "T"} or _is_adjacent_to_water(world.grid, Position(row, col)) or _is_adjacent_to_tree(world.grid, Position(row, col)):
            water_tree_coverage += 1
        north_score += max(0, len(world.grid) - 1 - row)

    return {
        "length": len(commands),
        "food_used": round(world.food_budget - food_left, 2),
        "fuel_used": round(world.fuel_budget - fuel_left, 2),
        "food_left": round(food_left, 2),
        "fuel_left": round(fuel_left, 2),
        "water_tree_coverage": water_tree_coverage,
        "north_score": north_score,
        "unique_cells": len(visited_cells),
    }


def _touches_goal(world: WorldState, commands: list[str]) -> bool:
    """Sprawdza, czy komendy prowadzą na pole celu `G`.

    Args:
        world: Dane świata.
        commands: Sekwencja komend.

    Returns:
        `True`, jeśli trasa odwiedza `G`.
    """

    row = world.start.row
    col = world.start.col
    for command in commands:
        delta = {
            "up": (-1, 0),
            "down": (1, 0),
            "left": (0, -1),
            "right": (0, 1),
        }.get(command)
        if delta is None:
            continue
        row += delta[0]
        col += delta[1]
        if row == world.goal.row and col == world.goal.col:
            return True
    return False


def candidates_to_json(candidates: list[RouteCandidate]) -> list[dict[str, Any]]:
    """Konwertuje listę kandydatów do postaci JSON.

    Args:
        candidates: Lista kandydackich tras.

    Returns:
        Lista słowników gotowych do zapisu.
    """

    return [
        {
            "name": candidate.name,
            "vehicle_name": candidate.vehicle_name,
            "commands": candidate.commands,
            "answer": candidate.to_answer(),
            "score": candidate.score,
            "metrics": candidate.metrics,
        }
        for candidate in candidates
    ]
