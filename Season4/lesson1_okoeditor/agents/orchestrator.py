"""Orkiestrator przepływu wykonania zadania `okoeditor`."""

from pathlib import Path

from config import AppSettings
from services.task_executor import OkoTaskExecutor
from utils.io import write_json
from utils.logger import log_info, log_warn


class OkoOrchestrator:
    """Koordynuje kolejne etapy realizacji zadania.

    Args:
        settings: Konfiguracja aplikacji.
        executor: Usługa realizująca kroki domenowe.
    """

    def __init__(self, settings: AppSettings, executor: OkoTaskExecutor) -> None:
        """Inicjalizuje orkiestrator.

        Args:
            settings: Obiekt konfiguracji.
            executor: Obiekt wykonawcy kroków zadania.
        """

        self._settings = settings
        self._executor = executor

    def run(self) -> None:
        """Wykonuje pełny przepływ orkiestracji zadania.

        Side Effects:
            Zapisuje artefakty pośrednie i końcowe do katalogu `output`.
        """

        log_info("Etap 1/4: pobranie help.")
        help_payload = self._executor.fetch_help()

        log_info("Etap 2/4: budowa planu akcji.")
        plan = self._executor.build_action_plan(help_payload=help_payload)

        actions = plan.get("actions", [])
        validation = plan.get("validation", {})
        has_todo = any(action.get("payload", {}).get("action") == "TODO" for action in actions)
        if has_todo or not validation.get("ok", False):
            log_warn("Plan akcji wymaga ręcznej korekty przed uruchomieniem etapu wykonania.")
            write_json(
                Path(self._settings.app_output_dir) / "manual_required.json",
                {
                    "status": "manual_input_required",
                    "reason": "Plan zawiera placeholdery lub nie przeszedł walidacji.",
                    "validation": validation,
                },
            )
            return

        log_info("Etap 3/4: wykonanie akcji.")
        summary = self._executor.run_actions(actions=actions)

        log_info("Etap 4/4: zakończenie done.")
        self._executor.finalize(summary=summary)
