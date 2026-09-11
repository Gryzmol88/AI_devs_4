"""Usługa realizacji kroków zadania `okoeditor`."""

import re
from pathlib import Path
from typing import Any

from clients.oko_api import OkoApiClient
from clients.oko_panel_reader import OkoPanelReader
from clients.openrouter_client import OpenRouterClient
from config import AppSettings
from models.schemas import ApiActionSnapshot, RunSummary
from services.id_resolver import OkoIdResolver
from utils.io import write_json, write_text
from utils.logger import log_info, log_warn


class OkoTaskExecutor:
    """Wykonuje kroki biznesowe związane z zadaniem `okoeditor`.

    Args:
        settings: Konfiguracja aplikacji.
        oko_client: Klient API centrali.
        openrouter_client: Klient API OpenRouter.
    """

    def __init__(
        self,
        settings: AppSettings,
        oko_client: OkoApiClient,
        openrouter_client: OpenRouterClient,
        panel_reader: OkoPanelReader,
        id_resolver: OkoIdResolver,
    ) -> None:
        """Inicjalizuje wykonawcę kroków zadania.

        Args:
            settings: Obiekt konfiguracji aplikacji.
            oko_client: Klient do komunikacji z API `verify`.
            openrouter_client: Klient do wsparcia planowania przez LLM.
            panel_reader: Klient odczytu danych z panelu OKO.
            id_resolver: Resolver rekordów i identyfikatorów.
        """

        self._settings = settings
        self._oko_client = oko_client
        self._openrouter_client = openrouter_client
        self._panel_reader = panel_reader
        self._id_resolver = id_resolver
        self._output_dir = Path(self._settings.app_output_dir)

    def fetch_help(self) -> dict[str, Any]:
        """Pobiera dokumentację dostępnych akcji z API.

        Returns:
            Surowa odpowiedź API dla akcji `help`.

        Side Effects:
            Zapisuje plik `step1_help.json` do katalogu `output`.
        """

        log_info("Pobieranie specyfikacji API (help).")
        response = self._oko_client.help()
        write_json(self._output_dir / "step1_help.json", response)
        return response

    def build_action_plan(self, help_payload: dict[str, Any]) -> dict[str, Any]:
        """Buduje plan akcji na bazie odpowiedzi `help`.

        Args:
            help_payload: Odpowiedź API z opisem dostępnych akcji.

        Returns:
            Plan w postaci słownika z gotowymi akcjami lub placeholderami.

        Side Effects:
            Zapisuje plan do `step2_action_plan.json`.
        """

        plan: dict[str, Any] = {
            "description": "Deterministyczny plan oparty o realne rekordy z panelu OKO.",
            "actions": [],
            "help_snapshot_hint": "Akcje i pola muszą być zgodne ze step1_help.json.",
        }

        panel_snapshot = self._panel_reader.fetch_snapshot()
        write_json(self._output_dir / "step2_panel_snapshot.json", panel_snapshot)
        write_json(self._output_dir / "step2_record_candidates.json", panel_snapshot.get("records", []))
        auth_meta = panel_snapshot.get("auth", {})
        if not auth_meta.get("ok", False):
            log_warn("Panel OKO nie jest uwierzytelniony. Nie uda się rozwiązać rekordów do update.")

        resolution = self._id_resolver.resolve(records=panel_snapshot.get("records", []))
        write_json(self._output_dir / "step2_resolved_ids.json", resolution)
        plan["resolution"] = resolution

        if self._settings.app_use_llm_planner and self._openrouter_client.is_enabled():
            log_info("Generowanie podpowiedzi planu przez OpenRouter.")
            llm_hint = self._generate_llm_plan_hint(help_payload=help_payload)
            plan["llm_hint"] = llm_hint
            write_text(self._output_dir / "step2_llm_raw.txt", llm_hint.get("raw_text", ""))
            plan["source"] = "deterministic_with_llm_hint"
        else:
            log_warn("Planer LLM pominięty (brak klucza lub wyłączona flaga).")
            plan["source"] = "deterministic_without_llm"

        plan["actions"] = self._build_actions_from_resolution(resolution=resolution)
        write_json(self._output_dir / "step2_payloads_final.json", plan["actions"])

        validation = self._validate_action_plan(actions=plan.get("actions", []))
        plan["validation"] = validation
        if not validation.get("ok", False):
            log_warn("Plan akcji nie przeszedł walidacji. Pozostawiono tryb manualny.")

        write_json(self._output_dir / "step2_action_plan.json", plan)
        write_json(self._output_dir / "step2_plan_validated.json", plan)
        return plan

    def run_actions(self, actions: list[dict[str, Any]]) -> RunSummary:
        """Wykonuje listę akcji API i zbiera podsumowanie.

        Args:
            actions: Lista słowników zawierających nazwę oraz payload akcji.

        Returns:
            Obiekt `RunSummary` z wynikami wykonania.

        Side Effects:
            Zapisuje snapshoty do `step3_actions.json`.
        """

        summary = RunSummary()
        for action in actions:
            action_name = str(action.get("name", "unnamed_action"))
            payload = action.get("payload", {})
            log_info(f"Wykonywanie akcji: {action_name}")

            response = self._oko_client.call_verify(answer=payload)
            snapshot = ApiActionSnapshot(
                action_name=action_name,
                payload=payload,
                response=response,
                ok=True,
            )
            summary.steps.append(snapshot)

        write_json(
            self._output_dir / "step3_actions.json",
            [item.model_dump() for item in summary.steps],
        )
        return summary

    def finalize(self, summary: RunSummary) -> RunSummary:
        """Kończy zadanie przez akcję `done`.

        Args:
            summary: Dotychczasowe podsumowanie działania.

        Returns:
            Zaktualizowane podsumowanie z odpowiedzią końcową.

        Side Effects:
            Zapisuje `final_result.json` i `final_result.txt` do `output`.
        """

        log_info("Wysyłanie akcji done.")
        final_response = self._oko_client.done()
        summary.final_response = final_response

        write_json(self._output_dir / "final_result.json", summary.model_dump())
        write_text(self._output_dir / "final_result.txt", str(final_response))
        return summary

    def _generate_llm_plan_hint(self, help_payload: dict[str, Any]) -> dict[str, Any]:
        """Generuje podpowiedź planu akcji z pomocą modelu.

        Args:
            help_payload: Odpowiedź `help` użyta jako kontekst.

        Returns:
            Słownik z sugestiami modelu. Gdy parsing się nie powiedzie,
            zwraca odpowiedź tekstową w polu `raw_text`.
        """

        prompt = (
            "Na podstawie odpowiedzi API zaproponuj JSON z kluczem `actions` i trzema payloadami akcji: "
            "1) zmiana klasyfikacji raportu Skolwin na zwierzęta, "
            "2) oznaczenie zadania Skolwin jako wykonane z notatką o bobrach, "
            "3) dodanie incydentu ruchu ludzi w Komarowie. "
            "Format elementu: {'name': '...', 'payload': {'action': '...', ...}}. "
            "Zwróć wyłącznie JSON bez komentarzy."
        )
        response = self._openrouter_client.chat(
            messages=[
                {"role": "system", "content": "Jesteś precyzyjnym asystentem API."},
                {
                    "role": "user",
                    "content": f"{prompt}\n\nOdpowiedź help:\n{help_payload}",
                },
            ],
            temperature=0.0,
            max_tokens=900,
        )

        choices = response.get("choices", [])
        if not choices:
            return {"raw_text": "", "warning": "Brak choices w odpowiedzi OpenRouter."}

        content = (
            choices[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return {"raw_text": content}

    def _validate_action_plan(self, actions: list[dict[str, Any]]) -> dict[str, Any]:
        """Waliduje plan akcji wymagany przez zadanie.

        Args:
            actions: Lista akcji do walidacji.

        Returns:
            Słownik z wynikiem walidacji (`ok`, `errors`, `count`).
        """

        errors: list[str] = []
        if len(actions) < 3:
            errors.append("Plan powinien zawierać co najmniej 3 akcje.")

        for index, action in enumerate(actions):
            if not isinstance(action, dict):
                errors.append(f"Akcja #{index + 1} nie jest obiektem.")
                continue

            payload = action.get("payload")
            if not isinstance(payload, dict):
                errors.append(f"Akcja #{index + 1} nie ma poprawnego payloadu.")
                continue

            action_value = str(payload.get("action", "")).strip()
            if not action_value:
                errors.append(f"Akcja #{index + 1} nie zawiera pola payload.action.")
            if action_value.upper() == "TODO":
                errors.append(f"Akcja #{index + 1} zawiera niedozwolony placeholder TODO.")

            page_value = str(payload.get("page", "")).strip()
            if page_value not in {"incydenty", "zadania", "notatki"}:
                errors.append(f"Akcja #{index + 1} ma niepoprawne payload.page.")

            record_id = str(payload.get("id", "")).strip()
            if not re.fullmatch(r"[a-fA-F0-9]{32}", record_id):
                errors.append(f"Akcja #{index + 1} zawiera niepoprawne payload.id.")

        return {"ok": len(errors) == 0, "errors": errors, "count": len(actions)}

    def _build_actions_from_resolution(self, resolution: dict[str, Any]) -> list[dict[str, Any]]:
        """Buduje finalne payloady `update` na podstawie rozwiązanych ID.

        Args:
            resolution: Wynik działania resolvera identyfikatorów.

        Returns:
            Lista akcji gotowych do wysłania przez API.
        """

        resolved = resolution.get("resolved", {})
        skolwin_incident = resolved.get("skolwin_incident", {})
        skolwin_task = resolved.get("skolwin_task", {})
        komarowo_incident = resolved.get("komarowo_incident", {})

        actions: list[dict[str, Any]] = []
        if skolwin_incident.get("id"):
            actions.append(
                {
                    "name": "update_skolwin_report_classification",
                    "payload": {
                        "action": "update",
                        "page": "incydenty",
                        "id": skolwin_incident["id"],
                        "title": "MOVE04 Wykryto zwierzęta w rejonie miasta Skolwin",
                        "content": "Zgłoszenie dotyczy zwierząt zauważonych w rejonie miasta Skolwin.",
                    },
                }
            )

        if skolwin_task.get("id"):
            actions.append(
                {
                    "name": "complete_skolwin_todo",
                    "payload": {
                        "action": "update",
                        "page": "zadania",
                        "id": skolwin_task["id"],
                        "title": "Zadanie wykonane: obserwacja zwierząt w rejonie Skolwin",
                        "content": "W rejonie Skolwin zaobserwowano zwierzęta, m.in. bobry.",
                        "done": "YES",
                    },
                }
            )

        if komarowo_incident.get("id"):
            actions.append(
                {
                    "name": "create_komarowo_incident",
                    "payload": {
                        "action": "update",
                        "page": "incydenty",
                        "id": komarowo_incident["id"],
                        "title": "MOVE01 Wykryto ruch ludzi w okolicach miasta Komarowo",
                        "content": "W okolicach miasta Komarowo wykryto ruch ludzi.",
                    },
                }
            )

        return actions
