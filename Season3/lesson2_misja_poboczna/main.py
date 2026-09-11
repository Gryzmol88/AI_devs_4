"""Punkt wejścia programu rozwiązującego misję poboczną lekcji 2."""

from __future__ import annotations

from pathlib import Path

from agent_loop import SideMissionRunner
from command_policy import CommandPolicy
from config import get_settings
from io_utils import (
    create_session_output_dir,
    ensure_output_dir,
    log_terminal,
    timestamp_utc,
    write_json,
)
from shell_api_client import ShellApiClient
from verify_client import VerifyClient


def main() -> None:
    """Uruchamia deterministiczny runner misji pobocznej.

    Efekty uboczne:
        Odczytuje konfigurację z `.env`, komunikuje się z API i zapisuje pliki sesji.
    """

    base_dir = Path(__file__).resolve().parent
    fallback_output_dir = ensure_output_dir(base_dir, "output")
    session_output_dir = create_session_output_dir(fallback_output_dir)

    log_terminal("Start programu (misja poboczna).")
    log_terminal(f"Sesja output: {session_output_dir}")

    try:
        log_terminal("Ładowanie konfiguracji z .env.")
        settings = get_settings()

        configured_root_output_dir = ensure_output_dir(base_dir, settings.output_dir_name)
        if configured_root_output_dir.resolve() != fallback_output_dir.resolve():
            session_output_dir = create_session_output_dir(configured_root_output_dir)
            log_terminal(f"Sesja output (config): {session_output_dir}")

        log_terminal(f"Task: {settings.side_task_name}")
        log_terminal(f"Binarka: {settings.side_task_binary_path}")

        runner = SideMissionRunner(
            settings=settings,
            shell_api=ShellApiClient(settings=settings),
            verify_api=VerifyClient(settings=settings),
            policy=CommandPolicy(),
            output_dir=session_output_dir,
        )

        result = runner.run()
        if result.get("success"):
            log_terminal("Misja poboczna zakończona sukcesem.")
        else:
            log_terminal("Nie wykryto poprawnego kodu w limicie kroków.")
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

