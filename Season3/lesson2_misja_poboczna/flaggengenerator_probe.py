"""Prober do testowania uruchomien /bin/flaggengenerator w shell API."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config import Settings, get_settings
from io_utils import (
    append_jsonl,
    create_session_output_dir,
    ensure_output_dir,
    log_terminal,
    timestamp_utc,
    write_json,
)
from shell_api_client import ShellApiClient


def _build_probe_commands() -> list[str]:
    """Buduje liste komend testujacych binarke flaggengenerator.

    Returns:
        Lista komend do sekwencyjnego wykonania.
    """

    base = "/bin/flaggengenerator"
    return [
        base,
        f"{base} --help",
        f"{base} -h",
        f"{base} Schmetterling",
        f"{base} schmetterling",
        f"{base} SCHMETTERLING",
        f"{base} Werkzeug",
        f"{base} Dings",
        f"{base} admin1",
        f"{base} admin",
        f"{base} -D",
    ]


@dataclass(slots=True)
class FlaggengeneratorProbe:
    """Realizuje probe uruchamiania /bin/flaggengenerator.

    Atrybuty:
        settings: Ustawienia aplikacji.
        shell_api: Klient shell API.
        output_dir: Katalog sesji output.
    """

    settings: Settings
    shell_api: ShellApiClient
    output_dir: Path

    @property
    def session_log_path(self) -> Path:
        """Zwraca sciezke pliku logu sesji.

        Returns:
            Sciezka pliku `probe_session_log.jsonl`.
        """

        return self.output_dir / "probe_session_log.jsonl"

    def _record_event(self, event: dict[str, Any]) -> None:
        """Dopisuje rekord zdarzenia do logu sesji.

        Args:
            event: Dane pojedynczego zdarzenia.
        """

        append_jsonl(self.session_log_path, {"timestamp": timestamp_utc(), **event})

    def run(self) -> dict[str, Any]:
        """Wykonuje wszystkie komendy probe i zapisuje artefakty.

        Returns:
            Podsumowanie probe.
        """

        commands = _build_probe_commands()
        attempts: list[dict[str, Any]] = []
        first_success_command: str | None = None
        first_success_response: dict[str, Any] | None = None

        for index, command in enumerate(commands, start=1):
            log_terminal(f"Probe {index}/{len(commands)}: {command}")
            result = self.shell_api.run_command(command)
            step_payload = {"command": command, **result}
            write_json(self.output_dir / f"probe_step{index:02d}.json", step_payload)
            self._record_event({"type": "probe_result", "step": index, "payload": step_payload})
            attempts.append(step_payload)

            if result.get("ok") and first_success_command is None:
                first_success_command = command
                response = result.get("response")
                first_success_response = response if isinstance(response, dict) else {}

        summary = {
            "success": first_success_command is not None,
            "first_success_command": first_success_command,
            "first_success_response": first_success_response,
            "attempts_count": len(attempts),
            "attempts": attempts,
        }
        write_json(self.output_dir / "probe_final_result.json", summary)
        return summary


def main() -> None:
    """Uruchamia probe /bin/flaggengenerator i zapisuje wyniki do output."""

    base_dir = Path(__file__).resolve().parent
    fallback_output_dir = ensure_output_dir(base_dir, "output")
    session_output_dir = create_session_output_dir(fallback_output_dir)

    log_terminal("Start programu (flaggengenerator probe).")
    log_terminal(f"Sesja output: {session_output_dir}")

    try:
        log_terminal("Ladowanie konfiguracji z .env.")
        settings = get_settings()
        configured_root_output_dir = ensure_output_dir(base_dir, settings.output_dir_name)
        if configured_root_output_dir.resolve() != fallback_output_dir.resolve():
            session_output_dir = create_session_output_dir(configured_root_output_dir)
            log_terminal(f"Sesja output (config): {session_output_dir}")

        probe = FlaggengeneratorProbe(
            settings=settings,
            shell_api=ShellApiClient(settings=settings),
            output_dir=session_output_dir,
        )
        result = probe.run()
        if result.get("success"):
            log_terminal("Probe zakonczony: wykryto odpowiedz sukcesu.")
        else:
            log_terminal("Probe zakonczony: brak sukcesu w zadanej liscie komend.")
    except Exception as error:  # noqa: BLE001
        log_terminal("Blad krytyczny. Zapis szczegolow do output/probe_fatal_error.json")
        write_json(
            session_output_dir / "probe_fatal_error.json",
            {
                "timestamp": timestamp_utc(),
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        raise


if __name__ == "__main__":
    main()
