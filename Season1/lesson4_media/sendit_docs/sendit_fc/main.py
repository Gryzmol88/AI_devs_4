"""CLI entrypoint for sendit function-calling agent."""

import argparse
import json
from pathlib import Path



DEFAULT_SYSTEM_PROMPT = """Jestes agentem wykonujacym task sendit przez function calling.
Koniecznie wykonaj narzedzia w logicznej kolejnosci:
1) fetch_docs_recursive
2) extract_nontext
3) build_declaration_from_rules
4) verify_sendit
Po otrzymaniu odpowiedzi z verify zakoncz i podsumuj wynik.
"""

DEFAULT_USER_PROMPT = (
    "Wykonaj task sendit: pobierz dokumentacje, przetworz zalaczniki, zbuduj deklaracje i zweryfikuj przez /verify."
)


def main() -> None:
    """Parse CLI args, run function-calling agent, and save execution trace.

    Side effects:
    - Reads runtime settings through Pydantic Settings.
    - Calls remote LLM API and downstream tools during the loop.
    - Writes JSON trace file to `--save-trace` path.

    Raises:
        RuntimeError: If required dependencies are missing.
    """


    parser = argparse.ArgumentParser(description="Sendit function-calling agent")
    parser.add_argument(
        "--workspace-dir",
        default=str(Path("lesson4_media") / "sendit_docs"),
        help="Workspace directory containing raw/ and parsed/.",
    )
    parser.add_argument(
        "--model",
        default="openai/gpt-5-mini",
        help="Model used for orchestration (function-calling loop).",
    )
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT)
    parser.add_argument("--user-prompt", default=DEFAULT_USER_PROMPT)
    parser.add_argument(
        "--save-trace",
        default=str(Path("lesson4_media") / "sendit_docs" / "parsed" / "fc_trace.json"),
        help="Where to save execution trace.",
    )
    args = parser.parse_args()

    from .settings import SenditSettings
    settings = SenditSettings()

    from .agent_loop import run_agent_loop
    from .tool_definitions import TOOLS
    from .tool_handlers import SenditToolHandlers

    try:
        from openai import OpenAI
    except ModuleNotFoundError as error:
        raise RuntimeError("Package openai is required. Install dependencies first.") from error

    client = OpenAI(api_key=settings.OPENROUTER_API_KEY, base_url=settings.OPENROUTER_BASE_URL)

    handlers = SenditToolHandlers(workspace_dir=Path(args.workspace_dir), settings=settings)
    result = run_agent_loop(
        client=client,
        model=args.model,
        tools=TOOLS,
        handlers=handlers,
        system_prompt=args.system_prompt,
        user_prompt=args.user_prompt,
        max_iterations=args.max_iterations,
    )

    trace_path = Path(args.save_trace)
    trace_path.parent.mkdir(parents=True, exist_ok=True)
    trace_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Status: {result['status']}")
    print(f"Iterations: {result['iterations']}")
    print(f"Trace saved to: {trace_path}")
    if result.get("final_message"):
        print("\nFinal message:\n")
        print(result["final_message"])


if __name__ == "__main__":
    main()

