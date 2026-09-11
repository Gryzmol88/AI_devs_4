"""Punkt wejścia dla misji pobocznej lekcji 5."""

from __future__ import annotations

from pathlib import Path
import traceback
from typing import Any

from clients.hub_client import HubClient
from clients.openrouter_client import OpenRouterClient
from config import get_settings
from models import Position, VehicleSpec, WorldState
from planner.beaver_route_planner import BeaverRoutePlanner, candidates_to_json
from utils.logger import configure_logger
from utils.output import create_session_dir, write_json, write_text


def main() -> None:
    """Uruchamia pipeline zdobywania flagi misji pobocznej.

    Efekty uboczne:
        Wysyła zapytania HTTP do endpointów huba i zapisuje artefakty do `output`.
    """

    settings = get_settings()
    logger = configure_logger("lesson5_side", settings.log_level)
    base_dir = Path(__file__).resolve().parent
    session_dir = create_session_dir(base_dir, settings.output_dir_name)

    write_json(
        session_dir / "step0_start.json",
        {
            "maps_url": settings.maps_url,
            "vehicles_url": settings.vehicles_url,
            "books_url": settings.books_url,
            "verify_url": settings.verify_url,
            "side_task_candidates": settings.parsed_task_candidates(),
            "side_max_attempts": settings.side_max_attempts,
        },
    )
    logger.info("Start programu")

    hub = HubClient(settings=settings)
    llm = OpenRouterClient(settings=settings)
    planner = BeaverRoutePlanner()

    try:
        logger.info("Etap 1/5: pobieranie mapy i notatek")
        map_payload = hub.fetch_map("Skolwin")
        books_payloads = _fetch_books_payloads(hub)
        write_json(session_dir / "step1_map.json", map_payload)
        write_json(session_dir / "step1_books.json", books_payloads)

        logger.info("Etap 2/5: pobieranie pojazdów")
        vehicle_payloads = _fetch_vehicle_payloads(hub)
        write_json(session_dir / "step2_vehicles.json", vehicle_payloads)

        logger.info("Etap 3/5: normalizacja danych")
        world = _build_world_state(map_payload=map_payload, vehicle_payloads=vehicle_payloads, books_payloads=books_payloads)
        write_json(session_dir / "step3_world_state.json", _world_to_json(world))

        logger.info("Etap 4/5: generowanie kandydatów tras")
        candidates = planner.generate_failure_exploration_candidates(world, max_routes=24)
        if not candidates:
            candidates = planner.generate_water_contact_candidates(world)
        if not candidates:
            candidates = planner.generate_river_patrol_candidates(world, max_steps=12)
        write_json(session_dir / "step4_candidates.json", candidates_to_json(candidates))

        logger.info("Etap 5/5: próby verify")
        task_candidates = settings.parsed_task_candidates()
        llm_candidates = llm.guess_task_names(
            hint="Tam są bobry! Side mission connected to savethem and beavers near northern water.",
            known_candidates=task_candidates,
        )
        for item in llm_candidates:
            if item not in task_candidates:
                task_candidates.append(item)
        if "savethem" in task_candidates:
            task_candidates = ["savethem", *[item for item in task_candidates if item != "savethem"]]
        task_candidates = ["savethem"]
        write_json(session_dir / "step5_task_candidates.json", {"task_candidates": task_candidates})

        result = _run_verify_attempts(
            hub=hub,
            task_candidates=task_candidates,
            route_candidates=candidates,
            max_attempts=settings.side_max_attempts,
            logger=logger,
            session_dir=session_dir,
        )
        write_json(session_dir / "final_result.json", result)
        write_text(session_dir / "final_result.txt", str(result))
        logger.info("Zakończono. Wynik zapisany do final_result.json")
    except Exception as error:  # noqa: BLE001
        logger.error("Błąd wykonania: %s", error)
        write_json(
            session_dir / "error.json",
            {"error": str(error), "traceback": traceback.format_exc()},
        )
        raise


def _fetch_books_payloads(hub: HubClient) -> list[dict[str, Any]]:
    """Pobiera zestaw notatek związanych z regułami ruchu.

    Args:
        hub: Klient API huba.

    Returns:
        Lista odpowiedzi endpointu books.
    """

    queries = [
        "I need notes about movement rules and terrain",
        "How does movement work on water, rocks and trees?",
        "Can each vehicle traverse W R T tiles?",
        "beavers north waterline",
        "vehicle selection and dismount rules",
    ]
    payloads: list[dict[str, Any]] = []
    for query in queries:
        payloads.append({"query": query, "response": hub.fetch_books(query)})
    return payloads


def _fetch_vehicle_payloads(hub: HubClient) -> list[dict[str, Any]]:
    """Pobiera parametry wszystkich dostępnych pojazdów.

    Args:
        hub: Klient API huba.

    Returns:
        Lista odpowiedzi endpointu wehicles.
    """

    payloads: list[dict[str, Any]] = []
    for vehicle_name in ["rocket", "horse", "walk", "car"]:
        try:
            payloads.append({"vehicle": vehicle_name, "response": hub.fetch_vehicle(vehicle_name)})
        except RuntimeError as error:
            payloads.append({"vehicle": vehicle_name, "error": str(error)})
    return payloads


def _build_world_state(
    map_payload: dict[str, Any],
    vehicle_payloads: list[dict[str, Any]],
    books_payloads: list[dict[str, Any]],
) -> WorldState:
    """Tworzy obiekt `WorldState` z danych API.

    Args:
        map_payload: Odpowiedź endpointu map.
        vehicle_payloads: Odpowiedzi endpointu pojazdów.
        books_payloads: Odpowiedzi endpointu books.

    Returns:
        Znormalizowany obiekt `WorldState`.
    """

    grid = map_payload.get("map")
    if not isinstance(grid, list) or not grid:
        raise ValueError("Brak poprawnej mapy w odpowiedzi endpointu maps.")

    start = _find_symbol(grid, "S")
    goal = _find_symbol(grid, "G")
    vehicles = _extract_vehicles(vehicle_payloads)

    notes: list[dict[str, Any]] = []
    for payload in books_payloads:
        response = payload.get("response", {})
        if isinstance(response, dict):
            for note in response.get("notes", []):
                if isinstance(note, dict):
                    notes.append(note)

    return WorldState(
        city_name=str(map_payload.get("cityName", "Skolwin")),
        grid=[[str(cell) for cell in row] for row in grid],
        start=start,
        goal=goal,
        vehicles=vehicles,
        books_notes=notes,
        fuel_budget=10.0,
        food_budget=10.0,
    )


def _find_symbol(grid: list[list[Any]], symbol: str) -> Position:
    """Wyszukuje pozycję symbolu na mapie.

    Args:
        grid: Mapa jako lista wierszy.
        symbol: Szukany symbol (`S` lub `G`).

    Returns:
        Pozycja symbolu.

    Raises:
        ValueError: Gdy symbol nie występuje na mapie.
    """

    for row_index, row in enumerate(grid):
        for col_index, value in enumerate(row):
            if str(value).upper() == symbol.upper():
                return Position(row=row_index, col=col_index)
    raise ValueError(f"Nie znaleziono symbolu {symbol} na mapie.")


def _extract_vehicles(vehicle_payloads: list[dict[str, Any]]) -> dict[str, VehicleSpec]:
    """Konwertuje odpowiedzi endpointu pojazdów na słownik specyfikacji.

    Args:
        vehicle_payloads: Lista odpowiedzi z endpointu pojazdów.

    Returns:
        Słownik `nazwa -> VehicleSpec`.
    """

    speeds = {"rocket": 3.0, "car": 2.0, "horse": 1.4, "walk": 1.0}
    vehicles: dict[str, VehicleSpec] = {}
    for item in vehicle_payloads:
        response = item.get("response")
        if not isinstance(response, dict):
            continue
        if response.get("code") != 230:
            continue
        name = str(response.get("name", "")).strip().lower()
        consumption = response.get("consumption", {})
        if not name or not isinstance(consumption, dict):
            continue
        fuel_value = consumption.get("fuel")
        food_value = consumption.get("food")
        if not isinstance(fuel_value, (int, float)) or not isinstance(food_value, (int, float)):
            continue
        vehicles[name] = VehicleSpec(
            name=name,
            fuel_per_step=float(fuel_value),
            food_per_step=float(food_value),
            speed=speeds.get(name, 1.0),
        )
    if "walk" not in vehicles:
        vehicles["walk"] = VehicleSpec(name="walk", fuel_per_step=0.0, food_per_step=2.5, speed=1.0)
    return vehicles


def _run_verify_attempts(
    hub: HubClient,
    task_candidates: list[str],
    route_candidates: list[Any],
    max_attempts: int,
    logger: Any,
    session_dir: Path,
) -> dict[str, Any]:
    """Wysyła próby do `/verify` aż do uzyskania flagi lub wyczerpania limitu.

    Args:
        hub: Klient huba.
        task_candidates: Lista kandydatów nazwy taska.
        route_candidates: Lista kandydatów trasy.
        max_attempts: Limit prób.
        logger: Logger terminalowy.
        session_dir: Katalog sesji do zapisu artefaktów.

    Returns:
        Podsumowanie przebiegu prób.
    """

    attempts: list[dict[str, Any]] = []
    attempt_index = 0
    for task_name in task_candidates:
        if not task_name.isalpha():
            continue
        for route in route_candidates:
            if attempt_index >= max_attempts:
                return {"status": "max_attempts_reached", "attempts": attempts}

            answer = route.to_answer()
            logger.info("Verify attempt %s task=%s route=%s", attempt_index + 1, task_name, route.name)
            attempt_payload = {
                "attempt": attempt_index + 1,
                "task": task_name,
                "route_name": route.name,
                "answer": answer,
            }
            try:
                response = hub.verify(task_name=task_name, answer=answer)
                attempt_payload["response"] = response
                write_json(session_dir / f"step5_attempt_{attempt_index + 1:03d}.json", attempt_payload)
                attempts.append(attempt_payload)

                message = str(response.get("message", ""))
                if "{FLG:INTACTCITY}" in message:
                    continue
                if "{FLG:" in message:
                    return {
                        "status": "flag_found",
                        "flag": message,
                        "attempt": attempt_index + 1,
                        "task": task_name,
                        "route_name": route.name,
                        "answer": answer,
                        "attempts": attempts,
                    }
            except RuntimeError as error:
                attempt_payload["error"] = str(error)
                write_json(session_dir / f"step5_attempt_{attempt_index + 1:03d}.json", attempt_payload)
                attempts.append(attempt_payload)
                if "{FLG:" in str(error) and "{FLG:INTACTCITY}" not in str(error):
                    return {
                        "status": "flag_found_in_error",
                        "flag": str(error),
                        "attempt": attempt_index + 1,
                        "task": task_name,
                        "route_name": route.name,
                        "answer": answer,
                        "attempts": attempts,
                    }
            attempt_index += 1
    return {"status": "not_found", "attempts": attempts}


def _prioritize_beaver_goal_candidates(candidates: list[Any]) -> list[Any]:
    """Sortuje kandydatów do celu według kryteriów "beaver friendly".

    Args:
        candidates: Kandydaci tras do celu.

    Returns:
        Posortowana i przefiltrowana lista kandydatów.
    """

    filtered: list[Any] = []
    for candidate in candidates:
        commands = getattr(candidate, "commands", [])
        metrics = getattr(candidate, "metrics", {})
        water_adjacent = int(metrics.get("water_adjacent_steps", 0))
        water_steps = int(metrics.get("water_steps", 0))
        if not isinstance(commands, list) or not commands:
            continue
        if len(commands) > 24:
            continue
        if water_adjacent < 3 and water_steps < 1:
            continue
        filtered.append(candidate)

    pool = filtered if filtered else list(candidates)
    pool.sort(
        key=lambda item: (
            -int(getattr(item, "metrics", {}).get("water_adjacent_steps", 0)),
            -int(getattr(item, "metrics", {}).get("water_steps", 0)),
            -int(getattr(item, "metrics", {}).get("north_score", 0)),
            len(getattr(item, "commands", [])),
        )
    )
    return pool


def _world_to_json(world: WorldState) -> dict[str, Any]:
    """Konwertuje `WorldState` do serializowalnego słownika.

    Args:
        world: Dane świata.

    Returns:
        Słownik JSON.
    """

    return {
        "city_name": world.city_name,
        "start": {"row": world.start.row, "col": world.start.col},
        "goal": {"row": world.goal.row, "col": world.goal.col},
        "fuel_budget": world.fuel_budget,
        "food_budget": world.food_budget,
        "grid": world.grid,
        "vehicles": {
            key: {
                "fuel_per_step": spec.fuel_per_step,
                "food_per_step": spec.food_per_step,
                "speed": spec.speed,
            }
            for key, spec in world.vehicles.items()
        },
        "books_notes_count": len(world.books_notes),
    }


if __name__ == "__main__":
    main()
