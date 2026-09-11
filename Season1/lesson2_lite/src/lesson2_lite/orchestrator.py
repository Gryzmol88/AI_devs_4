import json
import os
from pathlib import Path

from openai import OpenAI

from .agent.loop import extract_last_submit_result, run_agent_loop
from .api.hub_client import extract_verify_code, fetch_power_plants
from .config import bootstrap_env, get_hub_api_key, get_required_env
from .constants import ANSI_CYAN, ANSI_RESET
from .repository.suspects_repo import read_suspects
from .tools.handlers import ToolHandlers, write_json


def main() -> None:
    """
    Spina caly workflow Function Calling:
    - przygotowuje dane i klienta LLM,
    - uruchamia petle narzedzi,
    - zapisuje trace i wynik /verify.
    """
    print("[main] Start programu lesson2_lite")
    bootstrap_env()
    print("[main] Zmienne srodowiskowe zaladowane")

    openrouter_api_key = get_required_env("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_MODEL", "openai/gpt-5")
    max_iterations = int(os.getenv("MAX_ITERATIONS", "20"))
    hub_api_key = get_hub_api_key()
    print(f"[main] Model: {model}, max_iterations: {max_iterations}")

    base_dir = Path(__file__).resolve().parents[2]
    output_dir = base_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[main] Katalog output: {output_dir}")

    print("[main] Geokodowanie zewnetrznym API wylaczone; wspolrzedne miast poda LLM przez tool.")

    print("[main] Wczytuje podejrzanych...")
    suspects = read_suspects()
    print(f"[main] Podejrzani: {len(suspects)}")
    print("[main] Wczytuje elektrownie...")
    plants = fetch_power_plants(hub_api_key)
    print(f"[main] Elektrownie: {len(plants)}")

    if not suspects:
        raise ValueError("Lista podejrzanych jest pusta")
    if not plants:
        raise ValueError("Lista elektrowni jest pusta")

    client = OpenAI(api_key=openrouter_api_key, base_url="https://openrouter.ai/api/v1")
    print("[main] Klient OpenRouter gotowy")
    handlers = ToolHandlers(
        api_key=hub_api_key,
        suspects=suspects,
        plants=plants,
    )
    print("[main] Handlery narzedzi gotowe")

    trace_path = output_dir / "agent_trace.json"
    result = run_agent_loop(
        client=client,
        model=model,
        handlers=handlers,
        max_iterations=max_iterations,
        trace_path=trace_path,
    )
    print(f"[main] Petla agenta zakonczona: status={result['status']}, iterations={result['iterations']}")

    verify_response = extract_last_submit_result(result["messages"])

    summary = {
        "status": result["status"],
        "iterations": result["iterations"],
        "final_message": result["final_message"],
    }
    write_json(output_dir / "run_summary.json", summary)
    write_json(output_dir / "verify_response.json", verify_response)
    print("[main] Zapisano run_summary.json i verify_response.json")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    code = extract_verify_code(verify_response) if isinstance(verify_response, dict) else None
    status_code = verify_response.get("status_code") if isinstance(verify_response, dict) else None
    print(f"{ANSI_CYAN}[VERIFY:final]{ANSI_RESET} " f"http={status_code} code={code}")

