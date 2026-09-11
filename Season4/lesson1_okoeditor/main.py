"""Punkt wejścia aplikacji do realizacji zadania `okoeditor`."""

from datetime import datetime
from pathlib import Path

from agents.orchestrator import OkoOrchestrator
from clients.oko_api import OkoApiClient
from clients.oko_panel_reader import OkoPanelReader
from clients.openrouter_client import OpenRouterClient
from config import AppSettings
from services.id_resolver import OkoIdResolver
from services.task_executor import OkoTaskExecutor
from utils.io import ensure_dir, write_text
from utils.logger import log_error, log_info


def _configure_run_output_dir(settings: AppSettings) -> None:
    """Konfiguruje katalog wynikowy dla pojedynczego uruchomienia.

    Każde uruchomienie otrzymuje osobny katalog z timestampem, dzięki czemu
    artefakty poprzednich przebiegów nie są nadpisywane.

    Args:
        settings: Konfiguracja aplikacji do zaktualizowania.

    Side Effects:
        Tworzy katalog wynikowy bieżącego uruchomienia oraz zapisuje plik
        `latest_run.txt` w katalogu bazowym output.
    """

    base_output_dir = Path(settings.app_output_dir)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = base_output_dir / run_id

    ensure_dir(run_output_dir)
    settings.app_output_dir = str(run_output_dir)
    write_text(base_output_dir / "latest_run.txt", run_id)
    log_info(f"Katalog output dla bieżącego uruchomienia: {run_output_dir}")


def main() -> int:
    """Uruchamia główny przepływ aplikacji.

    Returns:
        Kod wyjścia procesu: `0` przy powodzeniu lub `1` przy błędzie.
    """

    try:
        log_info("Start programu.")
        settings = AppSettings()
        log_info("Konfiguracja załadowana.")
        _configure_run_output_dir(settings=settings)

        oko_client = OkoApiClient(settings=settings)
        openrouter_client = OpenRouterClient(settings=settings)
        panel_reader = OkoPanelReader(settings=settings)
        id_resolver = OkoIdResolver()
        executor = OkoTaskExecutor(
            settings=settings,
            oko_client=oko_client,
            openrouter_client=openrouter_client,
            panel_reader=panel_reader,
            id_resolver=id_resolver,
        )
        orchestrator = OkoOrchestrator(settings=settings, executor=executor)

        orchestrator.run()
        log_info("Koniec programu.")
        return 0
    except Exception as exc:  # noqa: BLE001
        log_error(f"Błąd krytyczny: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
