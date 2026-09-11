"""Punkt wejscia aplikacji realizujacej zadanie windpower."""

from datetime import datetime
from pathlib import Path

from clients.aidevs_api import AIDevsApiClient
from clients.openrouter_client import OpenRouterClient
from config import AppSettings
from output_writer import OutputWriter
from services.config_signer import ConfigSigner
from services.report_collector import ReportCollector
from services.wind_planner import WindPlanner
from services.windpower_orchestrator import WindpowerOrchestrator
from utils.io import ensure_dir
from utils.io import write_text
from utils.logger import log_error
from utils.logger import log_info


def _configure_run_output_dir(settings: AppSettings) -> Path:
    """Tworzy katalog output dla pojedynczego uruchomienia.

    Args:
        settings: Konfiguracja aplikacji.

    Returns:
        Sciezka katalogu output biezacego przebiegu.

    Side Effects:
        Tworzy katalog i aktualizuje plik latest_run.txt.
    """

    base_output_dir = Path(settings.app_output_dir)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_output_dir = base_output_dir / run_id

    ensure_dir(run_output_dir)
    write_text(base_output_dir / "latest_run.txt", run_id)
    settings.app_output_dir = str(run_output_dir)
    return run_output_dir


def main() -> int:
    """Uruchamia glowny workflow programu windpower.

    Returns:
        Kod wyjscia procesu: 0 przy sukcesie, 1 przy bledzie.
    """

    try:
        log_info("Start programu windpower.")
        settings = AppSettings()
        log_info("Konfiguracja zaladowana z Season4/.env.")
        run_output_dir = _configure_run_output_dir(settings=settings)
        log_info(f"Katalog output: {run_output_dir}")

        api_client = AIDevsApiClient(settings=settings)
        openrouter_client = OpenRouterClient(settings=settings)
        report_collector = ReportCollector(settings=settings, api_client=api_client)
        planner = WindPlanner()
        signer = ConfigSigner(api_client=api_client)
        output_writer = OutputWriter(output_dir=run_output_dir)
        orchestrator = WindpowerOrchestrator(
            api_client=api_client,
            openrouter_client=openrouter_client,
            report_collector=report_collector,
            planner=planner,
            signer=signer,
            output_writer=output_writer,
            service_window_seconds=settings.app_service_window_seconds,
        )

        result = orchestrator.run()
        log_info(f"Wynik finalny: {result}")
        log_info("Koniec programu.")
        return 0
    except Exception as exc:  # noqa: BLE001
        log_error(f"Blad krytyczny: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
