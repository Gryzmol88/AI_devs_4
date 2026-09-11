"""Serwis drugiego agenta: sterowanie dronem i iteracje z `/verify`."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx

from .config import build_runtime_config, load_settings
from .io_utils import append_trace, log, prepare_run_paths, write_json, write_text
from .schemas import CoordinateResult, DroneInstructionPlan

FLAG_RE = re.compile(r"\{FLG:[^}]+\}")


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any], timeout_seconds: int) -> tuple[dict[str, Any], int]:
    """Wysyła żądanie JSON i zwraca odpowiedź JSON oraz kod HTTP."""

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(url, headers=headers, json=payload)
    status_code = response.status_code
    body = response.json()
    return body, status_code


def _get_text(url: str, timeout_seconds: int) -> str:
    """Pobiera tekst z URL (używane do pobrania dokumentacji API drona)."""

    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.get(url)
    response.raise_for_status()
    return response.text


def _tool_definitions() -> list[dict[str, Any]]:
    """Definiuje dozwolone function-calle: tylko podstawowe sterowanie dronem."""

    return [
        {
            "type": "function",
            "function": {
                "name": "setEngineMode",
                "description": "Włącza lub wyłącza silniki drona.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {"type": "string", "enum": ["engineON", "engineOFF"]},
                    },
                    "required": ["mode"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setPower",
                "description": "Ustawia moc silników (0-100%).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                    },
                    "required": ["percent"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setDestinationObject",
                "description": "Ustawia formalny cel misji.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Kod obiektu, np. PWR6132PL."},
                    },
                    "required": ["code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setSector",
                "description": "Ustawia sektor docelowy jako kolumna i wiersz.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "col": {"type": "integer", "minimum": 1},
                        "row": {"type": "integer", "minimum": 1},
                    },
                    "required": ["col", "row"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setDestroy",
                "description": "Ustawia cel misji na zniszczenie obiektu.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setReturn",
                "description": "Ustawia cel misji na powrót do bazy po wykonaniu zadania.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "setAltitude",
                "description": "Ustawia wysokość lotu w metrach.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "meters": {"type": "integer", "minimum": 1, "maximum": 100},
                    },
                    "required": ["meters"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "flyToLocation",
                "description": "Uruchamia lot z aktualnymi ustawieniami.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "hardReset",
                "description": "Resetuje stan drona po nieudanych próbach.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finishPlan",
                "description": "Kończy budowę planu instrukcji.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "reasoning_short": {"type": "string"},
                    },
                    "required": ["reasoning_short"],
                },
            },
        },
    ]


def _openrouter_chat(
    openrouter_base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    timeout_seconds: int,
) -> tuple[dict[str, Any], int]:
    """Wysyła jedno wywołanie chat completions z function-calling do OpenRouter."""

    payload = {
        "model": model,
        "temperature": 0,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    return _post_json(
        url=f"{openrouter_base_url.rstrip('/')}/chat/completions",
        headers=headers,
        payload=payload,
        timeout_seconds=timeout_seconds,
    )


def _normalize_and_patch_instructions(instructions: list[str], coords: CoordinateResult, feedback: str | None) -> list[str]:
    """Normalizuje instrukcje i dokleja obowiązkowe komendy wynikające z feedbacku.

    Zasady:
    - zachowujemy kolejność wygenerowaną przez model,
    - usuwamy puste wpisy i duplikaty 1:1,
    - gwarantujemy obecność minimalnego rdzenia misji,
    - dla błędu mocy silników (`-880`) wymuszamy `set(engineON)` i `set(100%)`.
    """

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in instructions:
        text = item.strip()
        if not text:
            continue
        if text in seen:
            continue
        seen.add(text)
        cleaned.append(text)

    def ensure_before_fly(instruction: str) -> None:
        """Dodaje instrukcję przed `flyToLocation`, jeśli jej brakuje."""

        if instruction in cleaned:
            return
        if "flyToLocation" in cleaned:
            idx = cleaned.index("flyToLocation")
            cleaned.insert(idx, instruction)
        else:
            cleaned.append(instruction)

    ensure_before_fly("setDestinationObject(PWR6132PL)")
    ensure_before_fly(f"set({coords.col},{coords.row})")
    ensure_before_fly("set(destroy)")
    ensure_before_fly("set(return)")
    ensure_before_fly("set(100m)")
    if "flyToLocation" not in cleaned:
        cleaned.append("flyToLocation")

    if feedback and "engine power set to 0%" in feedback:
        ensure_before_fly("set(engineON)")
        ensure_before_fly("set(100%)")

    return cleaned


def _build_instructions_with_function_calling(
    coords: CoordinateResult,
    docs_excerpt: str,
    feedback: str | None,
    *,
    model: str,
    openrouter_base_url: str,
    openrouter_api_key: str,
    timeout_seconds: int,
    llm_trace_path: Path,
) -> DroneInstructionPlan:
    """Buduje instrukcje drona przez function-calling ograniczony do podstaw."""

    system_prompt = (
        "Jesteś agentem sterowania dronem. "
        "Masz używać WYŁĄCZNIE dostępnych funkcji sterowania. "
        "Masz przygotować minimalny poprawny zestaw instrukcji do wykonania misji. "
        "Dla lotu wymagane są: włączone silniki, ustawiona moc silników, sektor, cel obiektu i wysokość."
    )
    user_prompt = (
        "Dane wejściowe:\n"
        f"- sektor tamy: col={coords.col}, row={coords.row}\n"
        "- formalny cel obiektu: PWR6132PL\n"
        "- rzeczywisty zrzut ma trafić w tamę.\n\n"
        "Dokumentacja API drona (fragment):\n"
        f"{docs_excerpt}\n\n"
        f"Feedback z ostatniej próby: {feedback or 'brak'}\n"
        "Zbuduj sekwencję funkcji i zakończ przez finishPlan."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tools = _tool_definitions()

    instructions: list[str] = []
    reasoning_short = "Plan wygenerowany przez agenta sterowania."

    for step in range(1, 13):
        response_json, status_code = _openrouter_chat(
            openrouter_base_url=openrouter_base_url,
            api_key=openrouter_api_key,
            model=model,
            messages=messages,
            tools=tools,
            timeout_seconds=timeout_seconds,
        )
        with llm_trace_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"step": step, "status_code": status_code, "response": response_json},
                    ensure_ascii=False,
                )
                + "\n"
            )

        choice = (response_json.get("choices") or [{}])[0]
        assistant = choice.get("message", {})
        tool_calls = assistant.get("tool_calls") or []
        content = assistant.get("content")

        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if content is not None:
            assistant_msg["content"] = content
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        if not tool_calls:
            break

        stop = False
        for tool_call in tool_calls:
            name = tool_call["function"]["name"]
            raw_args = tool_call["function"].get("arguments") or "{}"
            args = json.loads(raw_args)

            if name == "setDestinationObject":
                instr = f"setDestinationObject({args['code']})"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setEngineMode":
                instr = f"set({args['mode']})"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setPower":
                instr = f"set({int(args['percent'])}%)"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setSector":
                instr = f"set({int(args['col'])},{int(args['row'])})"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setDestroy":
                instr = "set(destroy)"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setReturn":
                instr = "set(return)"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "setAltitude":
                instr = f"set({int(args['meters'])}m)"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "flyToLocation":
                instr = "flyToLocation"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "hardReset":
                instr = "hardReset"
                instructions.append(instr)
                tool_result = {"ok": True, "instruction": instr}
            elif name == "finishPlan":
                reasoning_short = str(args.get("reasoning_short", reasoning_short))
                tool_result = {"ok": True, "finish": True}
                stop = True
            else:
                tool_result = {"ok": False, "error": f"Nieznana funkcja: {name}"}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )

            if stop:
                break
        if stop:
            break

    if not instructions:
        instructions = [
            "set(engineON)",
            "set(100%)",
            "setDestinationObject(PWR6132PL)",
            f"set({coords.col},{coords.row})",
            "set(destroy)",
            "set(return)",
            "set(100m)",
            "flyToLocation",
        ]
        reasoning_short = "Użyto planu awaryjnego (fallback)."

    final_instructions = _normalize_and_patch_instructions(instructions, coords, feedback)
    return DroneInstructionPlan(instructions=final_instructions, reasoning_short=reasoning_short)


def run_pilot_agent(coords: CoordinateResult, output_root: Path | None = None) -> tuple[dict[str, Any], Path]:
    """Uruchamia drugiego agenta: budowa instrukcji + iteracje po `/verify`.

    Agent:
    1. Pobiera dokumentację API drona.
    2. Buduje instrukcje przez function-calling z minimalnym zestawem funkcji.
    3. Wysyła instrukcje do `/verify`.
    4. Reaguje na feedback i ponawia próbę, aż do flagi lub limitu prób.
    """

    lesson_dir = Path(__file__).resolve().parents[2]
    settings = load_settings(lesson_dir=lesson_dir)
    runtime_cfg = build_runtime_config(settings=settings, lesson_dir=lesson_dir)

    output_dir = output_root or runtime_cfg.output_dir
    paths = prepare_run_paths(output_dir)
    llm_trace_path = paths.run_dir / "llm_trace.jsonl"
    attempts_path = paths.run_dir / "verify_attempts.jsonl"

    write_json(paths.config_json, runtime_cfg.model_dump(mode="json"))
    append_trace(paths.trace_jsonl, "init", "Start agenta sterowania dronem", {"run_dir": str(paths.run_dir)})
    log(f"Start agenta pilota: {paths.run_dir}")

    docs_html = _get_text(runtime_cfg.drone_docs_url, runtime_cfg.request_timeout_seconds)
    docs_excerpt = docs_html[:12000]
    write_text(paths.run_dir / "drone_docs_excerpt.html", docs_excerpt)
    append_trace(
        paths.trace_jsonl,
        "docs_loaded",
        "Pobrano dokumentację API drona",
        {"url": runtime_cfg.drone_docs_url, "chars": len(docs_excerpt)},
    )
    log("Pobrano dokumentację API drona")

    feedback: str | None = None
    final_response: dict[str, Any] | None = None
    final_instructions: list[str] = []
    final_flag: str | None = None

    for attempt in range(1, runtime_cfg.max_verify_attempts + 1):
        log(f"Próba sterowania #{attempt}/{runtime_cfg.max_verify_attempts}")
        plan = _build_instructions_with_function_calling(
            coords=coords,
            docs_excerpt=docs_excerpt,
            feedback=feedback,
            model=runtime_cfg.pilot_model,
            openrouter_base_url=runtime_cfg.openrouter_base_url,
            openrouter_api_key=settings.openrouter_api_key.get_secret_value(),
            timeout_seconds=runtime_cfg.request_timeout_seconds,
            llm_trace_path=llm_trace_path,
        )

        payload = {
            "apikey": settings.hub_api_key.get_secret_value(),
            "task": runtime_cfg.task_name,
            "answer": {"instructions": plan.instructions},
        }
        verify_response, status_code = _post_json(
            url=runtime_cfg.verify_url,
            headers={"Content-Type": "application/json"},
            payload=payload,
            timeout_seconds=runtime_cfg.request_timeout_seconds,
        )

        final_response = verify_response
        final_instructions = plan.instructions

        attempt_event = {
            "attempt": attempt,
            "status_code": status_code,
            "instructions_count": len(plan.instructions),
            "reasoning_short": plan.reasoning_short,
            "verify_response": verify_response,
        }
        with attempts_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(attempt_event, ensure_ascii=False) + "\n")

        append_trace(
            paths.trace_jsonl,
            "verify_attempt",
            "Wysłano instrukcje do /verify",
            {
                "attempt": attempt,
                "status_code": status_code,
                "instructions_count": len(plan.instructions),
            },
        )
        log(f"/verify odpowiedział HTTP {status_code}, instrukcji: {len(plan.instructions)}")

        verify_text = json.dumps(verify_response, ensure_ascii=False)
        flag_match = FLAG_RE.search(verify_text)
        if flag_match:
            final_flag = flag_match.group(0)
            append_trace(paths.trace_jsonl, "done", "Otrzymano flagę końcową", {"flag": final_flag})
            log(f"Sukces: {final_flag}")
            break

        feedback = verify_text[:2000]

    result = {
        "ok": final_flag is not None,
        "flag": final_flag,
        "coordinates_used": coords.model_dump(),
        "final_instructions": final_instructions,
        "final_verify_response": final_response or {},
        "run_dir": str(paths.run_dir),
    }
    write_json(paths.result_json, result)
    write_text(
        paths.summary_txt,
        (
            f"Wynik agenta pilota\n"
            f"- status: {'OK' if result['ok'] else 'NIEUKOŃCZONE'}\n"
            f"- flaga: {result['flag']}\n"
            f"- użyte koordynaty: ({coords.col},{coords.row})\n"
            f"- liczba instrukcji finalnych: {len(final_instructions)}\n"
        ),
    )
    return result, paths.run_dir
