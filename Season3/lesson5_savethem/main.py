"""Punkt wejścia rozwiązania `savethem`."""

from __future__ import annotations

from pathlib import Path
import traceback

from agents.discovery_agent import DiscoveryAgent
from clients.openrouter_client import OpenRouterClient
from clients.tools_api_client import ToolsApiClient
from config import get_settings
from models.schemas import normalize_problem_data
from solver.route_solver import solution_to_dict, solve_route
from utils.logger import configure_logger
from utils.output import create_session_output_dir, write_json, write_text


def main() -> None:
    """Uruchamia pełny pipeline: discovery, normalizacja, solver i verify.

    Returns:
        `None`.

    Efekty uboczne:
        Wysyła żądania HTTP do zewnętrznych endpointów oraz zapisuje artefakty
        do katalogu `output/session_<timestamp>`.
    """

    settings = get_settings()
    logger = configure_logger(name="savethem", level=settings.log_level)
    base_dir = Path(__file__).resolve().parent
    session_dir = create_session_output_dir(base_dir, settings.output_dir_name)

    write_json(
        session_dir / "step0_start.json",
        {
            "task": settings.savethem_task_name,
            "toolsearch_url": settings.toolsearch_url,
            "verify_url": settings.verify_url,
            "openrouter_model": settings.openrouter_model,
            "discovery_iterations": settings.discovery_iterations,
        },
    )
    logger.info("Start programu")

    tools_client = ToolsApiClient(settings=settings)
    openrouter_client = OpenRouterClient(settings=settings)
    discovery_agent = DiscoveryAgent(
        tools_client=tools_client,
        openrouter_client=openrouter_client,
        logger=logger,
        iterations=settings.discovery_iterations,
        max_tool_calls_per_iteration=settings.discovery_max_tool_calls,
    )

    try:
        logger.info("Etap 1/4: discovery narzędzi i danych")
        discovery_result = discovery_agent.run(session_dir=session_dir)
        write_json(session_dir / "step1_discovery_result.json", discovery_result.raw_payloads)

        logger.info("Etap 2/4: normalizacja danych")
        problem = normalize_problem_data(
            raw_payloads=discovery_result.raw_payloads,
            default_food_budget=settings.default_food_budget,
            default_fuel_budget=settings.default_fuel_budget,
        )
        write_json(
            session_dir / "step2_normalized.json",
            {
                "grid": problem.grid,
                "start": {"row": problem.start.row, "col": problem.start.col},
                "goal": {"row": problem.goal.row, "col": problem.goal.col},
                "food_budget": problem.food_budget,
                "fuel_budget": problem.fuel_budget,
                "vehicles": [
                    {
                        "name": vehicle.name,
                        "fuel_per_step": vehicle.fuel_per_step,
                        "food_per_step": vehicle.food_per_step,
                        "speed": vehicle.speed,
                        "allowed_terrains": sorted(vehicle.allowed_terrains),
                    }
                    for vehicle in problem.vehicles
                ],
                "terrain_rules": {
                    key: {
                        "passable_on_foot": rule.passable_on_foot,
                        "passable_by_vehicle": rule.passable_by_vehicle,
                    }
                    for key, rule in problem.terrain_rules.items()
                },
            },
        )

        logger.info("Etap 3/4: obliczanie trasy")
        solution = solve_route(problem)
        solution_payload = solution_to_dict(solution)
        write_json(session_dir / "step3_solution.json", solution_payload)
        write_text(session_dir / "final_answer.txt", str(solution.to_verify_answer()))

        logger.info("Etap 4/4: wysyłka do verify")
        verify_response = tools_client.verify(solution.to_verify_answer())
        write_json(session_dir / "step4_verify_response.json", verify_response)
        write_json(
            session_dir / "final_result.json",
            {
                "answer": solution.to_verify_answer(),
                "verify_response": verify_response,
            },
        )
        logger.info("Zakończono. Odpowiedź i wynik verify zapisane w output.")
    except Exception as error:  # noqa: BLE001
        logger.error("Błąd wykonania: %s", error)
        write_json(
            session_dir / "error.json",
            {"error": str(error), "traceback": traceback.format_exc()},
        )
        raise


if __name__ == "__main__":
    main()

