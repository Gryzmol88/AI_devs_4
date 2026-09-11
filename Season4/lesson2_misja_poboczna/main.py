"""Punkt wejscia dla lesson2_misja_poboczna."""

from datetime import datetime
from pathlib import Path

from clients.aidevs_api import AIDevsApiClient
from config import AppSettings
from services.side_mission_runner import SideMissionRunner
from utils.io import ensure_dir
from utils.io import write_text
from utils.logger import log_error
from utils.logger import log_info
from utils.logger import set_log_file


def _configure_run_output_dir(settings: AppSettings) -> Path:
    base_output_dir = Path(settings.app_output_dir)
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_output_dir = base_output_dir / run_id

    ensure_dir(run_output_dir)
    write_text(base_output_dir / "latest_run.txt", run_id)
    settings.app_output_dir = str(run_output_dir)
    return run_output_dir


def main() -> int:
    try:
        settings = AppSettings()
        run_output_dir = _configure_run_output_dir(settings=settings)
        set_log_file(run_output_dir / "live_run.log")
        log_info(f"Output run: {run_output_dir}")

        api_client = AIDevsApiClient(settings=settings)
        runner = SideMissionRunner(
            settings=settings,
            api_client=api_client,
            run_output_dir=str(run_output_dir),
        )
        summary = runner.run()
        log_info(f"Summary: {summary}")
        return 0
    except Exception as exc:  # noqa: BLE001
        log_error(f"Blad krytyczny: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
