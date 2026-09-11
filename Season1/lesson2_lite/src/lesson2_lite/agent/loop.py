import json
from pathlib import Path
from typing import Any

from openai import OpenAI

from ..tools.definitions import TOOLS
from ..tools.handlers import ToolHandlers, write_json
from .prompts import SYSTEM_PROMPT, USER_PROMPT


def message_to_dict(message: Any) -> dict[str, Any]:
    """
    Konwertuje odpowiedz asystenta OpenAI do slownika wiadomosci utrzymywanego
    w historii konwersacji petli agenta.
    """
    payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
    if getattr(message, "tool_calls", None):
        payload["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.function.name, "arguments": call.function.arguments},
            }
            for call in message.tool_calls
        ]
    return payload


def run_agent_loop(
    *,
    client: OpenAI,
    model: str,
    handlers: ToolHandlers,
    max_iterations: int,
    trace_path: Path,
) -> dict[str, Any]:
    """
    Uruchamia petle Function Calling: model wybiera narzedzia, kod je wykonuje,
    a wyniki wracaja do modelu az do finalnej odpowiedzi albo limitu iteracji.
    """
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT},
    ]
    trace: list[dict[str, Any]] = []
    print(f"[agent] Start petli Function Calling, max_iterations={max_iterations}")

    for iteration in range(1, max_iterations + 1):
        print(f"[agent] Iteracja {iteration}: wysylam zapytanie do modelu...")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )
        message = response.choices[0].message
        messages.append(message_to_dict(message))
        trace.append({"iteration": iteration, "assistant": message.content, "tool_calls": bool(message.tool_calls)})

        if not message.tool_calls:
            print(f"[agent] Iteracja {iteration}: model zwrocil finalna odpowiedz (bez tool_calls).")
            write_json(trace_path, trace)
            return {
                "status": "completed",
                "iterations": iteration,
                "final_message": message.content or "",
                "messages": messages,
            }

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            print(f"[agent] Iteracja {iteration}: wywolanie narzedzia `{tool_name}`")
            try:
                args = json.loads(tool_call.function.arguments or "{}")
            except Exception:  # noqa: BLE001
                args = {}

            result = handlers.dispatch(tool_name, args if isinstance(args, dict) else {})
            if result.get("ok") is True:
                print(f"[agent] Iteracja {iteration}: `{tool_name}` zakonczone OK")
            else:
                print(f"[agent] Iteracja {iteration}: `{tool_name}` blad -> {result.get('error')}")
            trace.append({"iteration": iteration, "tool": tool_name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool_name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    write_json(trace_path, trace)
    return {
        "status": "max_iterations_reached",
        "iterations": max_iterations,
        "final_message": "Stopped due to max iteration limit.",
        "messages": messages,
    }


def extract_last_submit_result(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Znajduje ostatni wynik narzedzia submit_findhim_answer z historii i zwraca go
    do zapisania jako osobny artefakt.
    """
    for message in reversed(messages):
        if message.get("role") != "tool":
            continue
        if message.get("name") != "submit_findhim_answer":
            continue
        content = message.get("content", "{}")
        try:
            raw = json.loads(content)
            if isinstance(raw, dict):
                data = raw.get("data")
                return data if isinstance(data, dict) else raw
        except Exception:  # noqa: BLE001
            pass
    return {"ok": False, "error": "No submit_findhim_answer call found"}

