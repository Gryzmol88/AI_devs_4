"""Punkt wejścia programu rozwiązującego zadanie firmware."""

from __future__ import annotations

from pathlib import Path

from agent_loop import FirmwareAgentRunner
from command_policy import CommandPolicy
from config import get_settings
from io_utils import (
    create_session_output_dir,
    ensure_output_dir,
    log_terminal,
    timestamp_utc,
    write_json,
)
from openrouter_client import (
    OpenRouterClient,
    OpenRouterContextLimitError,
    OpenRouterInvalidRequestError,
    OpenRouterLimitError,
)
from shell_api_client import ShellApiClient
from verify_client import VerifyClient


def main() -> None:
    """Uruchamia aplikację i pętlę agentową.

    Efekty uboczne:
        Odczytuje konfigurację z `.env`, komunikuje się z API oraz zapisuje pliki w `output`.
    """

    base_dir = Path(__file__).resolve().parent
    fallback_output_dir = ensure_output_dir(base_dir, "output")
    session_output_dir = create_session_output_dir(fallback_output_dir)
    log_terminal("Start programu.")
    log_terminal(f"Sesja output: {session_output_dir}")

    try:
        log_terminal("Ładowanie konfiguracji z .env.")
        settings = get_settings()

        configured_root_output_dir = ensure_output_dir(base_dir, settings.output_dir_name)
        if configured_root_output_dir.resolve() != fallback_output_dir.resolve():
            session_output_dir = create_session_output_dir(configured_root_output_dir)
            log_terminal(f"Sesja output (config): {session_output_dir}")

        log_terminal(f"Model OpenRouter: {settings.openrouter_model}")

        runner = FirmwareAgentRunner(
            settings=settings,
            openrouter=OpenRouterClient(settings=settings),
            shell_api=ShellApiClient(settings=settings),
            verify_api=VerifyClient(settings=settings),
            policy=CommandPolicy(),
            output_dir=session_output_dir,
            prompts_dir=base_dir / "prompts",
        )

        log_terminal("Uruchamianie pętli agentowej.")
        result = runner.run()
        if result.get("success"):
            log_terminal("Zadanie zakończone sukcesem.")
        else:
            log_terminal("Zadanie nie zostało zakończone sukcesem w limicie kroków.")
    except OpenRouterLimitError as error:
        log_terminal(
            "Przerwano: limit OpenRouter (402). Sprawdź kredyty klucza lub zmniejsz limit tokenów."
        )
        write_json(
            session_output_dir / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "action_hint": (
                    "Uzupełnij kredyty OpenRouter albo zmniejsz max_tokens w requestach."
                ),
                "original_error": error.original_error,
            },
        )
        return
    except OpenRouterContextLimitError as error:
        log_terminal(
            "Przerwano: limit kontekstu OpenRouter (400). Zmniejsz historię lub wielkość payloadów."
        )
        write_json(
            session_output_dir / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "action_hint": (
                    "Skróć historię wiadomości, ogranicz dane narzędzi i/lub zmniejsz max_tokens."
                ),
                "original_error": error.original_error,
            },
        )
        return
    except OpenRouterInvalidRequestError as error:
        log_terminal(
            "Przerwano: OpenRouter zwrócił 400 invalid request. Sprawdź format komunikacji narzędziowej."
        )
        write_json(
            session_output_dir / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
                "action_hint": (
                    "Sprawdź spójność tool_call_id między assistant.tool_calls i tool_result."
                ),
                "original_error": error.original_error,
            },
        )
        return
    except Exception as error:  # noqa: BLE001
        log_terminal("Błąd krytyczny. Zapis szczegółów do output/fatal_error.json")
        write_json(
            session_output_dir / "fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        raise


if __name__ == "__main__":
    main()
