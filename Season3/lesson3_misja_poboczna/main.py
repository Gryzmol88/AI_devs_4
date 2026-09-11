"""Punkt wejścia programu "tam i z powrotem" dla misji pobocznej lesson3."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from config import get_settings
from decision_engine import ThereAndBackEngine
from http_utils import HttpRequestError
from io_utils import (
    create_session_output_dir,
    ensure_output_dir,
    log_terminal,
    timestamp_utc,
    write_json,
    write_text,
)
from models import find_flag_in_payload, parse_board_state, to_serializable_state
from reactor_api_client import ReactorApiClient


def main() -> None:
    """Uruchamia program prowadzący robota do celu i z powrotem na start.

    Efekty uboczne:
        Odczytuje konfigurację z `.env`, wykonuje żądania do `/verify`
        i zapisuje pełne artefakty działania w `output`.
    """

    base_dir = Path(__file__).resolve().parent
    default_output = ensure_output_dir(base_dir, "output")
    session_output = create_session_output_dir(default_output)

    log_terminal("Start programu there-and-back (lesson3 side).")
    log_terminal(f"Sesja output: {session_output}")

    try:
        settings = get_settings()
        configured_output = ensure_output_dir(base_dir, settings.output_dir_name)
        if configured_output.resolve() != default_output.resolve():
            session_output = create_session_output_dir(configured_output)
            log_terminal(f"Sesja output (config): {session_output}")

        pre_flag_target_col = max(2, min(6, settings.pre_flag_target_col))
        api_client = ReactorApiClient(settings=settings)
        engine = ThereAndBackEngine(max_wait_streak=settings.max_wait_streak)

        log_terminal("Komenda start.")
        start_response = api_client.send_command("start")
        state = parse_board_state(start_response)
        first_flag = find_flag_in_payload(start_response)

        if settings.echo_full_response:
            print(start_response)

        write_json(
            session_output / "step000_start.json",
            {
                "timestamp": timestamp_utc(),
                "phase": "start",
                "command": "start",
                "state": to_serializable_state(state),
                "flag": first_flag,
                "raw_response": start_response,
            },
        )

        best_flag = first_flag
        phase = "to_pre_flag"
        phase_target_col = pre_flag_target_col
        phase_waits_remaining = 0
        wait_streak = 0

        final_payload: dict[str, Any] | None = None

        for step in range(1, settings.max_steps_total + 1):
            if phase_waits_remaining > 0:
                command = "wait"
                reason = f"phase_waits_remaining={phase_waits_remaining}"
                safe = True
                phase_waits_remaining -= 1
            else:
                decision = engine.choose(
                    state=state,
                    target_col=phase_target_col,
                    wait_streak=wait_streak,
                )
                command = decision.command
                reason = decision.reason
                safe = decision.safe

            if command == "wait":
                wait_streak += 1
            else:
                wait_streak = 0

            log_terminal(
                f"Krok {step}: phase={phase} target_col={phase_target_col} command={command} reason={reason}"
            )

            response = api_client.send_command(command)
            if settings.echo_full_response:
                print(response)

            parsed = parse_board_state(response)
            flag = find_flag_in_payload(response)
            if flag:
                best_flag = flag
                log_terminal(f"Wykryto flagę: {flag}")

            write_json(
                session_output / f"step{step:03d}_{phase}_{command}.json",
                {
                    "timestamp": timestamp_utc(),
                    "step": step,
                    "phase": phase,
                    "target_col": phase_target_col,
                    "command": command,
                    "decision": {
                        "reason": reason,
                        "safe": safe,
                        "wait_streak": wait_streak,
                    },
                    "state": to_serializable_state(parsed),
                    "flag": flag,
                    "raw_response": response,
                },
            )

            state = parsed

            if phase == "to_pre_flag" and state.robot_col >= pre_flag_target_col:
                log_terminal("Faza 1 zakończona: osiągnięto pole przed flagą.")
                phase = "to_start"
                phase_target_col = 1
                phase_waits_remaining = settings.phase_completion_waits
                wait_streak = 0
            elif phase == "to_start" and state.robot_col <= 1:
                log_terminal("Faza 2 zakończona: powrót na start.")
                phase_waits_remaining = settings.phase_completion_waits
                final_payload = {
                    "timestamp": timestamp_utc(),
                    "success": True,
                    "message": "Zrealizowano trase tam i z powrotem.",
                    "steps": step,
                    "best_flag": best_flag,
                    "final_phase": phase,
                    "final_state": to_serializable_state(state),
                    "last_response": response,
                }
                break

        if final_payload is None:
            final_payload = {
                "timestamp": timestamp_utc(),
                "success": False,
                "message": "Osiagnieto limit krokow przed zakonczeniem obu faz.",
                "steps": settings.max_steps_total,
                "best_flag": best_flag,
                "final_phase": phase,
                "final_state": to_serializable_state(state),
            }

        write_json(session_output / "final_result.json", final_payload)
        write_text(
            session_output / "final_result.txt",
            (
                f"success={final_payload.get('success')}\n"
                f"message={final_payload.get('message')}\n"
                f"steps={final_payload.get('steps')}\n"
                f"best_flag={final_payload.get('best_flag') or '-'}\n"
                f"final_phase={final_payload.get('final_phase')}\n"
            ),
        )

        if final_payload.get("best_flag"):
            print(final_payload["best_flag"])

        log_terminal("Koniec programu.")

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


if __name__ == "__main__":
    main()
