import json

from openai import OpenAI

from .agent.loop import run_agent_loop
from .agent.prompts import SYSTEM_PROMPT, USER_PROMPT
from .agent.state import AgentState
from .api.hub_client import HubClient
from .config import Settings
from .models import PowerPlant
from .repository.plants_repo import load_plants, save_plants
from .repository.suspects_repo import load_suspects
from .tools.definitions import TOOLS
from .tools.handlers import ToolHandlers, write_json


def _get_client(settings: Settings) -> OpenAI:
    return OpenAI(api_key=settings.OPENROUTER_API_KEY, base_url="https://openrouter.ai/api/v1")


def _load_or_fetch_plants(settings: Settings, hub: HubClient) -> list[PowerPlant]:
    cached = load_plants(settings.plants_cache_path)
    if cached:
        return cached

    raw = hub.fetch_power_plants()
    save_plants(settings.plants_cache_path, raw)
    return [PowerPlant(code=i["code"], lat=i["lat"], lon=i["lon"]) for i in raw]


def run() -> None:
    settings = Settings()
    suspects = load_suspects(settings.suspects_path, settings.fallback_suspects_path)
    hub = HubClient(settings)
    plants = _load_or_fetch_plants(settings, hub)

    client = _get_client(settings)
    handlers = ToolHandlers(settings=settings, hub=hub, suspects=suspects, plants=plants)
    state = AgentState(trace_path=settings.trace_path)

    result = run_agent_loop(
        client=client,
        model=settings.OPENROUTER_MODEL,
        tools=TOOLS,
        handlers=handlers,
        state=state,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=USER_PROMPT,
        max_iterations=settings.MAX_ITERATIONS,
    )

    summary = {
        "status": result["status"],
        "iterations": result["iterations"],
        "final_message": result["final_message"],
    }
    write_json(settings.report_output_path, summary)

    final_tool_results = [step for step in state.steps if step.get("tool") == "submit_findhim_answer"]
    verify_payload = final_tool_results[-1]["result"] if final_tool_results else {"ok": False, "error": "No submit"}
    write_json(settings.verify_output_path, verify_payload)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Trace: {settings.trace_path}")
    print(f"Verify result: {settings.verify_output_path}")

