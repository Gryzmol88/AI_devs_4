"""Orkiestrator pelnego przeplywu zadania windpower."""

from __future__ import annotations

import time
from typing import Any

from clients.aidevs_api import AIDevsApiClient
from clients.openrouter_client import OpenRouterClient
from output_writer import OutputWriter
from services.config_signer import ConfigSigner
from services.report_collector import ReportCollector
from services.wind_planner import WindPlanner
from utils.logger import log_info
from utils.logger import log_warn


class WindpowerOrchestrator:
    """Realizuje sekwencje API: start, raporty, config, turbinecheck, done."""

    def __init__(
        self,
        api_client: AIDevsApiClient,
        openrouter_client: OpenRouterClient,
        report_collector: ReportCollector,
        planner: WindPlanner,
        signer: ConfigSigner,
        output_writer: OutputWriter,
        service_window_seconds: int,
    ) -> None:
        """Inicjalizuje wszystkie zaleznosci orchestratora.

        Args:
            api_client: Klient API verify.
            openrouter_client: Klient OpenRouter do pomocy diagnostycznej.
            report_collector: Kolektor raportow asynchronicznych.
            planner: Planner harmonogramu.
            signer: Podpisywanie konfiguracji unlockCode.
            output_writer: Serwis zapisu artefaktow.
            service_window_seconds: Limit czasu okna serwisowego.
        """

        self._api_client = api_client
        self._openrouter_client = openrouter_client
        self._report_collector = report_collector
        self._planner = planner
        self._signer = signer
        self._output_writer = output_writer
        self._service_window_seconds = service_window_seconds

    def run(self) -> dict[str, Any]:
        """Uruchamia pelny workflow zadania windpower.

        Returns:
            Odpowiedz API po akcji `done`.
        """

        log_info("Start okna serwisowego.")
        service_started = self._api_client.start()
        self._output_writer.save_json("step1_start.json", service_started)
        start_monotonic = time.monotonic()

        log_info("Pobieranie help.")
        help_response = self._api_client.help()
        self._output_writer.save_json("step2_help.json", help_response)

        report_params = self._select_report_params(help_response=help_response)
        self._output_writer.save_json("step3_selected_params.json", {"params": report_params})
        log_info(f"Wybrane parametry raportowe: {', '.join(report_params)}")

        documentation_response = self._api_client.get(param="documentation")
        self._output_writer.save_json("step3b_documentation.json", documentation_response)

        enqueued = self._report_collector.enqueue_params(params=report_params)
        self._output_writer.save_json("step4_enqueued.json", enqueued)

        reports = self._report_collector.collect_results(expected_sources=set(report_params))
        reports["documentation"] = documentation_response
        self._output_writer.save_json("step5_reports_raw.json", reports)
        self._output_writer.save_json("step5b_getresult_trace.json", self._report_collector.get_last_trace())

        context = self._planner.build_context(reports=reports)
        planning_result = self._planner.plan(context=context)
        self._output_writer.save_planning_result("step6_plan.json", planning_result)
        log_info("Plan harmonogramu gotowy.")

        if self._openrouter_client.is_enabled():
            self._run_optional_llm_review(reports=reports)

        configs_payload = self._signer.build_configs_payload(planning_result.configs)
        self._output_writer.save_json("step7_configs_signed.json", configs_payload)
        log_info("Wygenerowano unlockCode dla wszystkich punktow.")

        config_response = self._api_client.call({"action": "config", "configs": configs_payload})
        self._output_writer.save_json("step8_config_response.json", config_response)
        log_info("Konfiguracja wyslana.")

        initial_turbine_check = reports.get("turbinecheck", {})
        self._output_writer.save_json("step9_turbinecheck.json", initial_turbine_check)
        self._output_writer.save_json("step9b_getresult_trace.json", [])
        log_info("Test turbiny potwierdzony z wczesniejszego raportu.")

        done_response = self._api_client.done()
        self._output_writer.save_json("step10_done.json", done_response)
        self._output_writer.save_text("final_result.txt", str(done_response))
        log_info("Akcja done wyslana.")

        elapsed = time.monotonic() - start_monotonic
        self._output_writer.save_json("step11_timing.json", {"elapsed_seconds": elapsed})
        if elapsed > self._service_window_seconds:
            log_warn(
                "Workflow trwal dluzej niz deklarowany limit okna serwisowego. "
                "Sprawdz latencje i liczbe wywolan API."
            )
        return done_response

    def _run_optional_llm_review(self, reports: dict[str, dict[str, Any]]) -> None:
        """Uruchamia pomocnicza recenzje raportow przez OpenRouter.

        Args:
            reports: Raporty zebrane z API.

        Side Effects:
            Zapisuje dodatkowy artefakt z odpowiedzia OpenRouter.
        """

        log_info("Uruchomiono opcjonalna analize OpenRouter.")
        prompt = (
            "Przeanalizuj dane JSON i zwroc krotkie ostrzezenia dla planowania turbiny. "
            "Formatuj odpowiedz jako JSON z polem notes."
        )
        response = self._openrouter_client.analyze_json(
            system_prompt=prompt,
            user_payload=reports,
        )
        self._output_writer.save_json("step6b_llm_review.json", response)

    @staticmethod
    def _select_report_params(help_response: dict[str, Any]) -> list[str]:
        """Wybiera parametry raportowe na podstawie tresci help.

        Args:
            help_response: Odpowiedz API dla akcji help.

        Returns:
            Lista parametrow akcji `get` do kolejkowania.
        """

        available_params = WindpowerOrchestrator._extract_get_params(help_response=help_response)
        preferred = ["weather", "turbinecheck", "powerplantcheck"]
        chosen = [name for name in preferred if name in available_params]
        if not chosen:
            chosen = [name for name in available_params if name != "documentation"]
        if not chosen:
            chosen = preferred
        return chosen

    @staticmethod
    def _extract_get_params(help_response: dict[str, Any]) -> list[str]:
        """Wydobywa dozwolone parametry akcji `get` z odpowiedzi help.

        Args:
            help_response: Dane z API help.

        Returns:
            Lista parametrow.
        """

        actions = help_response.get("actions")
        if isinstance(actions, dict):
            get_action = actions.get("get")
            if isinstance(get_action, dict):
                values = get_action.get("paramValues")
                if isinstance(values, list):
                    return [value for value in values if isinstance(value, str)]
        return []
