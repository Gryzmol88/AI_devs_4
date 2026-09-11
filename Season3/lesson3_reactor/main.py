"""Punkt wejścia rozwiązania zadania reactor."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import get_settings
from decision_engine import ReactorDecisionEngine
from http_utils import HttpRequestError
from io_utils import (
    create_session_output_dir,
    ensure_output_dir,
    log_terminal,
    timestamp_utc,
    write_json,
    write_text,
)
from models import find_possible_flag, parse_board_state, to_serializable_state
from reactor_api_client import ReactorApiClient


def main() -> None:
    """Uruchamia pętlę sterowania robotem dla zadania reactor.

    Efekty uboczne:
        Odczytuje konfigurację z `.env`, wykonuje żądania HTTP do `/verify`
        oraz zapisuje kroki i wynik końcowy do katalogu `output`.
    """

    base_dir = Path(__file__).resolve().parent
    output_root = ensure_output_dir(base_dir, "output")
    session_output = create_session_output_dir(output_root)

    log_terminal("Start programu reactor.")
    log_terminal(f"Sesja output: {session_output}")

    try:
        settings = get_settings()
        configured_output_root = ensure_output_dir(base_dir, settings.output_dir_name)
        if configured_output_root.resolve() != output_root.resolve():
            session_output = create_session_output_dir(configured_output_root)
            log_terminal(f"Sesja output (config): {session_output}")

        log_terminal("Ładowanie klienta API i silnika decyzji.")
        api_client = ReactorApiClient(settings=settings)
        engine = ReactorDecisionEngine()

        log_terminal("Wysyłanie komendy start.")
        start_response = api_client.send_command("start")
        state = parse_board_state(start_response)
        start_flag = find_possible_flag(start_response)

        write_json(
            session_output / "step000_start.json",
            {
                "timestamp": timestamp_utc(),
                "command": "start",
                "state": to_serializable_state(state),
                "raw_response": start_response,
                "flag_hint": start_flag,
            },
        )

        if state.reached_goal or _response_is_terminal_success(start_response):
            _save_final_success(
                session_output=session_output,
                steps=0,
                state=state,
                response=start_response,
                flag_hint=start_flag,
            )
            log_terminal("Cel osiągnięty po komendzie start.")
            return

        wait_streak = 0
        last_response: dict[str, Any] = start_response
        final_flag_hint = start_flag

        for step_idx in range(1, settings.max_steps + 1):
            decision = engine.choose_command(state=state, wait_streak=wait_streak)
            command = decision.command

            if command == "wait":
                wait_streak += 1
            else:
                wait_streak = 0

            log_terminal(
                f"Krok {step_idx}: command={command} reason={decision.reason} safety={decision.safety}"
            )
            response = api_client.send_command(command)
            parsed_state = parse_board_state(response)
            flag_hint = find_possible_flag(response)
            if flag_hint:
                final_flag_hint = flag_hint

            write_json(
                session_output / f"step{step_idx:03d}_{command}.json",
                {
                    "timestamp": timestamp_utc(),
                    "step": step_idx,
                    "command": command,
                    "decision": {
                        "reason": decision.reason,
                        "safety": decision.safety,
                        "wait_streak": wait_streak,
                    },
                    "state": to_serializable_state(parsed_state),
                    "raw_response": response,
                    "flag_hint": flag_hint,
                },
            )

            state = parsed_state
            last_response = response

            if state.reached_goal or _response_is_terminal_success(response):
                _save_final_success(
                    session_output=session_output,
                    steps=step_idx,
                    state=state,
                    response=response,
                    flag_hint=final_flag_hint,
                )
                log_terminal(f"Cel osiągnięty w kroku {step_idx}.")
                return

        _save_final_failure(
            session_output=session_output,
            steps=settings.max_steps,
            state=state,
            response=last_response,
            flag_hint=final_flag_hint,
        )
        log_terminal("Nie osiągnięto celu w limicie kroków.")

    except HttpRequestError as error:
        log_terminal("Błąd HTTP podczas komunikacji z API reactor.")
        write_json(
            session_output / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "status_code": error.status_code,
            },
        )
        raise
    except Exception as error:  # noqa: BLE001
        log_terminal("Błąd krytyczny. Szczegóły zapisane w fatal_error.json")
        write_json(
            session_output / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        raise


def _response_is_terminal_success(response: dict[str, Any]) -> bool:
    """Sprawdza, czy odpowiedź API sygnalizuje sukces końcowy.

    Args:
        response: Surowa odpowiedź API.

    Returns:
        `True`, gdy treść odpowiedzi sugeruje pomyślne zakończenie.
    """

    success_keys = ["success", "ok", "completed", "done"]
    for key in success_keys:
        if isinstance(response.get(key), bool) and response.get(key):
            return True

    message = str(response.get("message", "")).lower()
    if any(token in message for token in ("success", "zaliczone", "gratul", "correct")):
        return True

    return False


def _save_final_success(
    session_output: Path,
    steps: int,
    state: Any,
    response: dict[str, Any],
    flag_hint: str | None,
) -> None:
    """Zapisuje artefakty końcowe dla udanej próby.

    Args:
        session_output: Katalog sesji output.
        steps: Liczba wykonanych kroków.
        state: Ostatni znormalizowany stan planszy.
        response: Ostatnia odpowiedź API.
        flag_hint: Opcjonalny tekst potencjalnej flagi.

    Efekty uboczne:
        Zapisuje `final_result.json` i `final_result.txt`.
    """

    payload = {
        "timestamp": timestamp_utc(),
        "success": True,
        "steps": steps,
        "state": to_serializable_state(state),
        "flag_hint": flag_hint,
        "raw_response": response,
    }
    write_json(session_output / "final_result.json", payload)
    write_text(
        session_output / "final_result.txt",
        f"SUCCESS\nsteps={steps}\nflag_hint={flag_hint or '-'}\n",
    )


def _save_final_failure(
    session_output: Path,
    steps: int,
    state: Any,
    response: dict[str, Any],
    flag_hint: str | None,
) -> None:
    """Zapisuje artefakty końcowe dla nieudanej próby.

    Args:
        session_output: Katalog sesji output.
        steps: Liczba wykonanych kroków.
        state: Ostatni znormalizowany stan planszy.
        response: Ostatnia odpowiedź API.
        flag_hint: Opcjonalny tekst potencjalnej flagi.

    Efekty uboczne:
        Zapisuje `final_result.json` i `final_result.txt`.
    """

    payload = {
        "timestamp": timestamp_utc(),
        "success": False,
        "steps": steps,
        "state": to_serializable_state(state),
        "flag_hint": flag_hint,
        "raw_response": response,
    }
    write_json(session_output / "final_result.json", payload)
    write_text(
        session_output / "final_result.txt",
        f"FAIL\nsteps={steps}\nflag_hint={flag_hint or '-'}\n",
    )


if __name__ == "__main__":
    main()
