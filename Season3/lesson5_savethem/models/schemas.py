"""Modele danych i normalizacja danych wejściowych dla zadania `savethem`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class Position:
    """Reprezentuje pozycję na mapie.

    Atrybuty:
        row: Wiersz na siatce mapy.
        col: Kolumna na siatce mapy.
    """

    row: int
    col: int


@dataclass(slots=True, frozen=True)
class Vehicle:
    """Opisuje pojazd i koszt ruchu przypisany do pojedynczego kroku.

    Atrybuty:
        name: Nazwa pojazdu widoczna w odpowiedzi `/verify`.
        fuel_per_step: Zużycie paliwa na krok.
        food_per_step: Zużycie jedzenia na krok.
        speed: Prędkość względna wykorzystywana do wyliczania czasu trasy.
        allowed_terrains: Zbiór typów terenu możliwych do pokonania.
    """

    name: str
    fuel_per_step: float
    food_per_step: float
    speed: float
    allowed_terrains: frozenset[str]


@dataclass(slots=True, frozen=True)
class TerrainRule:
    """Opisuje reguły przejścia po konkretnym typie terenu.

    Atrybuty:
        name: Nazwa terenu.
        passable_on_foot: Czy teren jest dostępny pieszo.
        passable_by_vehicle: Czy teren jest dostępny pojazdami.
    """

    name: str
    passable_on_foot: bool
    passable_by_vehicle: bool


@dataclass(slots=True)
class ProblemData:
    """Łączy wszystkie informacje potrzebne do wyznaczenia trasy.

    Atrybuty:
        grid: Mapa 10x10 zapisana jako lista wierszy.
        start: Pole startowe.
        goal: Pole docelowe (Skolwin).
        food_budget: Dostępny budżet jedzenia.
        fuel_budget: Dostępny budżet paliwa.
        vehicles: Lista pojazdów startowych.
        terrain_rules: Zasady przechodzenia przez teren.
    """

    grid: list[list[str]]
    start: Position
    goal: Position
    food_budget: float
    fuel_budget: float
    vehicles: list[Vehicle]
    terrain_rules: dict[str, TerrainRule]


@dataclass(slots=True)
class Solution:
    """Reprezentuje wynik działania solvera.

    Atrybuty:
        vehicle_name: Nazwa wybranego pojazdu startowego.
        moves: Lista ruchów (`up`, `down`, `left`, `right`).
        total_time: Łączny czas przejścia trasy.
        fuel_used: Zużyte paliwo.
        food_used: Zużyte jedzenie.
    """

    vehicle_name: str
    moves: list[str]
    total_time: float
    fuel_used: float
    food_used: float

    def to_verify_answer(self) -> list[str]:
        """Buduje finalną tablicę odpowiedzi dla endpointu `/verify`.

        Returns:
            Lista zawierająca nazwę pojazdu i kolejne ruchy.
        """

        return [self.vehicle_name, *self.moves]


def normalize_problem_data(
    raw_payloads: dict[str, Any],
    default_food_budget: int,
    default_fuel_budget: int,
) -> ProblemData:
    """Normalizuje surowe dane z narzędzi do postaci wymaganej przez solver.

    Args:
        raw_payloads: Surowe dane zgromadzone w etapie discovery.
        default_food_budget: Domyślny budżet jedzenia używany przy braku danych.
        default_fuel_budget: Domyślny budżet paliwa używany przy braku danych.

    Returns:
        Ujednolicony obiekt `ProblemData`.
    """

    grid = _extract_grid(raw_payloads)
    start = _extract_position(raw_payloads, aliases=("start", "from", "source"), fallback_symbol="S")
    goal = _extract_position(raw_payloads, aliases=("goal", "target", "skolwin"), fallback_symbol="G")

    budgets = _extract_budgets(raw_payloads)
    extracted_food = float(budgets.get("food", default_food_budget))
    extracted_fuel = float(budgets.get("fuel", default_fuel_budget))
    food_budget = float(default_food_budget if extracted_food < default_food_budget else extracted_food)
    fuel_budget = float(default_fuel_budget if extracted_fuel < default_fuel_budget else extracted_fuel)

    terrain_rules = _extract_terrain_rules(raw_payloads)
    vehicles = _extract_vehicles(raw_payloads, terrain_rules)
    if not vehicles:
        vehicles = [
            Vehicle(
                name="on_foot",
                fuel_per_step=0.0,
                food_per_step=1.0,
                speed=1.0,
                allowed_terrains=frozenset(
                    terrain_name
                    for terrain_name, rule in terrain_rules.items()
                    if rule.passable_on_foot
                ),
            )
        ]

    return ProblemData(
        grid=grid,
        start=start,
        goal=goal,
        food_budget=food_budget,
        fuel_budget=fuel_budget,
        vehicles=vehicles,
        terrain_rules=terrain_rules,
    )


def _extract_grid(raw_payloads: dict[str, Any]) -> list[list[str]]:
    """Wyszukuje mapę w surowym payloadzie i zwraca ją jako siatkę znaków.

    Args:
        raw_payloads: Wszystkie dane zebrane przez discovery.

    Returns:
        Mapa jako lista wierszy.

    Raises:
        ValueError: Gdy nie uda się odnaleźć poprawnej siatki mapy.
    """

    candidates = _collect_nested_by_keys(raw_payloads, {"map", "grid", "terrain"})
    for candidate in candidates:
        grid = _coerce_grid(candidate)
        if grid:
            return grid

    fallback_candidates = _collect_all_nested_values(raw_payloads)
    for candidate in fallback_candidates:
        grid = _coerce_grid(candidate)
        if grid and len(grid) == 10 and len(grid[0]) == 10:
            return grid
    raise ValueError("Nie udało się odnaleźć mapy 10x10 w danych discovery.")


def _coerce_grid(value: Any) -> list[list[str]]:
    """Próbuje zinterpretować wartość jako mapę.

    Args:
        value: Dowolna wartość z payloadu.

    Returns:
        Siatka mapy lub pusta lista, jeśli konwersja się nie powiedzie.
    """

    if isinstance(value, str):
        rows = [line.strip() for line in value.splitlines() if line.strip()]
        if rows and all(len(row) == len(rows[0]) for row in rows):
            return [list(row) for row in rows]
        return []

    if isinstance(value, list) and value:
        if all(isinstance(row, str) for row in value):
            rows = [row.strip() for row in value if row.strip()]
            if rows and all(len(row) == len(rows[0]) for row in rows):
                return [list(row) for row in rows]
        if all(isinstance(row, list) for row in value):
            grid: list[list[str]] = []
            for row in value:
                row_values = [str(cell) for cell in row]
                grid.append(row_values)
            if grid and all(len(row) == len(grid[0]) for row in grid):
                return grid
    return []


def _extract_position(raw_payloads: dict[str, Any], aliases: tuple[str, ...], fallback_symbol: str) -> Position:
    """Wydobywa pozycję startu lub celu z danych.

    Args:
        raw_payloads: Surowe dane discovery.
        aliases: Alternatywne nazwy pola pozycji.
        fallback_symbol: Symbol mapy wykorzystywany jako fallback.

    Returns:
        Odnaleziona pozycja.
    """

    keys = set(aliases)
    candidates = _collect_nested_by_keys(raw_payloads, keys)
    for candidate in candidates:
        parsed = _coerce_position(candidate)
        if parsed is not None:
            return parsed

    grid = _extract_grid(raw_payloads)
    for row_index, row in enumerate(grid):
        for col_index, value in enumerate(row):
            if str(value).upper() == fallback_symbol.upper():
                return Position(row=row_index, col=col_index)

    return Position(row=0, col=0) if fallback_symbol.upper() == "S" else Position(row=len(grid) - 1, col=len(grid[0]) - 1)


def _coerce_position(value: Any) -> Position | None:
    """Konwertuje różne formaty danych pozycji na `Position`.

    Args:
        value: Kandydat pozycji.

    Returns:
        Obiekt `Position` albo `None` przy braku dopasowania.
    """

    if isinstance(value, dict):
        row = value.get("row", value.get("y"))
        col = value.get("col", value.get("x"))
        if isinstance(row, (int, float)) and isinstance(col, (int, float)):
            return Position(row=int(row), col=int(col))

    if isinstance(value, list) and len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
        return Position(row=int(value[0]), col=int(value[1]))
    return None


def _extract_budgets(raw_payloads: dict[str, Any]) -> dict[str, float]:
    """Wydobywa limity zasobów z danych discovery.

    Args:
        raw_payloads: Surowe dane discovery.

    Returns:
        Słownik z kluczami `food` oraz `fuel` jeśli odnaleziono.
    """

    budgets: dict[str, float] = {}
    for candidate in _collect_all_nested_values(raw_payloads):
        if not isinstance(candidate, dict):
            continue
        lowered_keys = {str(key).lower() for key in candidate.keys()}
        if "consumption" in lowered_keys:
            continue
        if not ({"initial", "start", "budget", "resource", "resources"} & lowered_keys):
            continue
        for key in ("food", "food_budget", "provisions"):
            value = candidate.get(key)
            if isinstance(value, (int, float)):
                budgets["food"] = float(value)
                break
        for key in ("fuel", "fuel_budget", "gas"):
            value = candidate.get(key)
            if isinstance(value, (int, float)):
                budgets["fuel"] = float(value)
                break
    return budgets


def _extract_terrain_rules(raw_payloads: dict[str, Any]) -> dict[str, TerrainRule]:
    """Tworzy słownik zasad dla terenów.

    Args:
        raw_payloads: Surowe dane discovery.

    Returns:
        Mapowanie typu terenu na regułę.
    """

    defaults = {
        ".": TerrainRule(name=".", passable_on_foot=True, passable_by_vehicle=True),
        "S": TerrainRule(name="S", passable_on_foot=True, passable_by_vehicle=True),
        "G": TerrainRule(name="G", passable_on_foot=True, passable_by_vehicle=True),
        "T": TerrainRule(name="T", passable_on_foot=True, passable_by_vehicle=True),
        "R": TerrainRule(name="R", passable_on_foot=False, passable_by_vehicle=False),
        "W": TerrainRule(name="W", passable_on_foot=True, passable_by_vehicle=True),
        "#": TerrainRule(name="#", passable_on_foot=False, passable_by_vehicle=False),
    }

    candidates = _collect_nested_by_keys(raw_payloads, {"terrains", "terrain_rules", "tiles", "legend"})
    for candidate in candidates:
        parsed = _coerce_terrain_rules(candidate)
        if parsed:
            defaults.update(parsed)
    return defaults


def _coerce_terrain_rules(value: Any) -> dict[str, TerrainRule]:
    """Konwertuje dane legendy mapy na słownik reguł terenowych.

    Args:
        value: Kandydat legendy/zasad.

    Returns:
        Słownik reguł terenowych.
    """

    rules: dict[str, TerrainRule] = {}
    if isinstance(value, dict):
        for terrain_key, payload in value.items():
            if not isinstance(terrain_key, str):
                continue
            if isinstance(payload, dict):
                on_foot = bool(payload.get("passable_on_foot", payload.get("on_foot", True)))
                by_vehicle = bool(payload.get("passable_by_vehicle", payload.get("by_vehicle", True)))
                rules[terrain_key] = TerrainRule(
                    name=terrain_key,
                    passable_on_foot=on_foot,
                    passable_by_vehicle=by_vehicle,
                )
    return rules


def _extract_vehicles(raw_payloads: dict[str, Any], terrain_rules: dict[str, TerrainRule]) -> list[Vehicle]:
    """Wydobywa listę pojazdów i ich parametry zużycia zasobów.

    Args:
        raw_payloads: Surowe dane discovery.
        terrain_rules: Zasady terenowe używane jako fallback dla przejazdów.

    Returns:
        Lista gotowych obiektów `Vehicle`.
    """

    vehicles: list[Vehicle] = []
    candidates = _collect_nested_by_keys(raw_payloads, {"vehicles", "transport", "vehicle_list"})
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        for row in candidate:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", row.get("vehicle", "")).strip())
            if not name:
                continue
            fuel_per_step = float(row.get("fuel_per_step", row.get("fuel_cost", row.get("fuel", 1.0))))
            food_per_step = float(row.get("food_per_step", row.get("food_cost", row.get("food", 1.0))))
            speed = float(row.get("speed", row.get("velocity", 1.0)))
            allowed = row.get("allowed_terrains", row.get("allowed_tiles"))
            if isinstance(allowed, list):
                allowed_terrains = frozenset(str(item) for item in allowed)
            else:
                allowed_terrains = frozenset(
                    terrain_name
                    for terrain_name, rule in terrain_rules.items()
                    if rule.passable_by_vehicle
                )
            vehicles.append(
                Vehicle(
                    name=name,
                    fuel_per_step=fuel_per_step,
                    food_per_step=food_per_step,
                    speed=max(speed, 0.1),
                    allowed_terrains=allowed_terrains,
                )
            )

    direct_objects = _collect_all_nested_values(raw_payloads)
    for candidate in direct_objects:
        if not isinstance(candidate, dict):
            continue
        code = candidate.get("code")
        name = candidate.get("name")
        consumption = candidate.get("consumption")
        if code != 230 or not isinstance(name, str) or not isinstance(consumption, dict):
            continue
        fuel = consumption.get("fuel")
        food = consumption.get("food")
        if not isinstance(fuel, (int, float)) or not isinstance(food, (int, float)):
            continue
        normalized_name = name.strip().lower()
        if any(v.name.lower() == normalized_name for v in vehicles):
            continue
        vehicles.append(
            Vehicle(
                name=normalized_name,
                fuel_per_step=float(fuel),
                food_per_step=float(food),
                speed=_default_speed_for_vehicle(normalized_name),
                allowed_terrains=_default_allowed_terrains_for_vehicle(normalized_name, terrain_rules),
            )
        )
    return vehicles


def _default_speed_for_vehicle(vehicle_name: str) -> float:
    """Zwraca domyślną prędkość względną dla znanego środka transportu.

    Args:
        vehicle_name: Nazwa środka transportu.

    Returns:
        Współczynnik prędkości używany do optymalizacji czasu.
    """

    if vehicle_name == "rocket":
        return 3.0
    if vehicle_name == "car":
        return 2.0
    if vehicle_name == "horse":
        return 1.4
    return 1.0


def _default_allowed_terrains_for_vehicle(
    vehicle_name: str, terrain_rules: dict[str, TerrainRule]
) -> frozenset[str]:
    """Buduje domyślne tereny dla znanych pojazdów zgodnie z notatkami z `books`.

    Args:
        vehicle_name: Nazwa środka transportu.
        terrain_rules: Zbiór znanych symboli terenu.

    Returns:
        Zbiór symboli terenu możliwych do pokonania.
    """

    base = {name for name in terrain_rules if name != "R" and name != "#"}
    if vehicle_name in {"rocket", "car"}:
        return frozenset(name for name in base if name != "W")
    return frozenset(base)


def _collect_nested_by_keys(data: Any, keys: set[str]) -> list[Any]:
    """Przechodzi rekurencyjnie po strukturze i zbiera wartości pod wybranymi kluczami.

    Args:
        data: Dowolna struktura JSON.
        keys: Zbiór nazw kluczy do wyszukania.

    Returns:
        Lista wartości znalezionych pod podanymi kluczami.
    """

    results: list[Any] = []
    lowered = {key.lower() for key in keys}

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(key, str) and key.lower() in lowered:
                    results.append(value)
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return results


def _collect_all_nested_values(data: Any) -> list[Any]:
    """Zbiera wszystkie wartości terminalne i pośrednie z obiektu JSON.

    Args:
        data: Dowolna struktura zagnieżdżona.

    Returns:
        Lista wartości do dalszych prób normalizacji.
    """

    results: list[Any] = []

    def walk(node: Any) -> None:
        results.append(node)
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return results
