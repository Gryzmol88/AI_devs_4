"""Runner wykonujący sekwencję probe'ów dla misji pobocznej."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from .api_client import VerifyApiClient
from .config import AppSettings
from .io_utils import create_run_output_dir, write_json, write_text
from .models import ProbeResult
from .probes import (
    build_flag_ord_check_steps,
    build_flag_ord_with_main_steps,
    build_probe_steps,
)


class SideMissionRunner:
    """Wykonuje z góry przygotowaną sekwencję kroków diagnostycznych."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje runner i zależności.

        Args:
            settings: Ustawienia aplikacji.
        """

        self._settings = settings
        self._api = VerifyApiClient(settings=settings)
        self.last_output_dir: Path | None = None

    def _save_latest_run(self, run_dir: Path) -> None:
        """Aktualizuje wskaźnik ostatniego uruchomienia.

        Args:
            run_dir: Katalog bieżącego uruchomienia.

        Returns:
            None: Funkcja zapisuje `latest_run.txt`.
        """

        write_text(self._settings.output_path / "latest_run.txt", str(run_dir))

    def _select_steps(self) -> list:
        """Wybiera listę kroków na podstawie trybu działania.

        Returns:
            list: Lista obiektów `ProbeStep`.
        """

        if self._settings.app_mode == "check_flag_ord":
            return build_flag_ord_check_steps(submit_done=self._settings.submit_done)
        if self._settings.app_mode == "check_flag_ord_with_main":
            return build_flag_ord_with_main_steps(submit_done=self._settings.submit_done)
        return build_probe_steps()

    def _extract_flag_listing_validation(self, results: list[ProbeResult]) -> dict[str, Any]:
        """Waliduje hint `FLAG -> 70 76 65 71` na podstawie `listFiles /flag`.

        Args:
            results: Wyniki wszystkich wykonanych kroków.

        Returns:
            dict[str, Any]: Raport walidacji rozmiarów i kolejności.
        """

        expected_size_order = [70, 76, 65, 71]
        report: dict[str, Any] = {
            "mode": self._settings.app_mode,
            "expected_size_order": expected_size_order,
            "listing_found": False,
            "size_order_check_ok": False,
            "details": {},
        }
        target = next((item for item in results if "list_flag" in item.id), None)
        if target is None or not target.ok:
            return report

        entries = target.response.get("entries", [])
        if not isinstance(entries, list):
            return report

        report["listing_found"] = True
        normalized_entries: list[dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            normalized_entries.append(
                {
                    "name": name,
                    "size": entry.get("size"),
                    "created_at": entry.get("created_at"),
                }
            )

        # Najpierw próbujemy kolejność zwróconą przez API (naturalna kolejność listingu).
        observed_sizes_from_listing = [
            int(item["size"])
            for item in normalized_entries
            if isinstance(item.get("size"), int)
        ]
        report["details"]["entries"] = normalized_entries
        report["details"]["observed_sizes_from_listing"] = observed_sizes_from_listing

        # Dodatkowy widok: kolejność po nazwie (często tak działa ls -la).
        by_name_order = sorted(normalized_entries, key=lambda item: item["name"])
        observed_sizes_by_name = [
            int(item["size"])
            for item in by_name_order
            if isinstance(item.get("size"), int)
        ]
        report["details"]["observed_sizes_by_name"] = observed_sizes_by_name

        report["size_order_check_ok"] = (
            observed_sizes_from_listing == expected_size_order
            or observed_sizes_by_name == expected_size_order
        )
        report["overall_ok"] = report["size_order_check_ok"]
        return report

    def run(self) -> dict[str, Any]:
        """Uruchamia pełną sekwencję eksploracji API.

        Returns:
            dict[str, Any]: Podsumowanie wykonania.
        """

        self._settings.output_path.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_output_dir(self._settings.output_path)
        self.last_output_dir = run_dir

        results: list[ProbeResult] = []
        traces: list[dict[str, Any]] = []

        try:
            steps = self._select_steps()
            write_json(
                run_dir / "step0_plan.json",
                [step.model_dump() for step in steps],
            )
            print(f"[lesson4_side] Tryb: {self._settings.app_mode}")
            print(f"[lesson4_side] Liczba probe'ów: {len(steps)}")

            for index, step in enumerate(steps, start=1):
                print(f"[lesson4_side] {index}/{len(steps)} -> {step.id}")
                try:
                    response, trace = self._api.call(answer=step.answer)
                    traces.append(trace)
                    results.append(
                        ProbeResult(
                            id=step.id,
                            description=step.description,
                            ok=True,
                            response=response,
                        )
                    )
                except requests.HTTPError as exc:
                    response_payload: dict[str, Any] = {
                        "error": str(exc),
                    }
                    if exc.response is not None:
                        response_payload["status_code"] = exc.response.status_code
                        response_payload["body"] = exc.response.text
                    traces.append(
                        {
                            "request": {"task": self._settings.task_name, "answer": step.answer},
                            "http": {
                                "statusCode": exc.response.status_code if exc.response is not None else None,
                                "ok": False,
                            },
                            "response": response_payload,
                        }
                    )
                    results.append(
                        ProbeResult(
                            id=step.id,
                            description=step.description,
                            ok=False,
                            response=response_payload,
                        )
                    )

            write_json(
                run_dir / "step1_probe_results.json",
                [result.model_dump() for result in results],
            )
            write_json(run_dir / "step2_http_trace.json", traces)
            if self._settings.app_mode in {"check_flag_ord", "check_flag_ord_with_main"}:
                validation = self._extract_flag_listing_validation(results)
                write_json(run_dir / "step3_flag_ord_validation.json", validation)
                print(
                    "[lesson4_side] Check FLAG size-order:",
                    "OK" if validation.get("size_order_check_ok") else "NOK",
                )

            summary = {
                "task": self._settings.task_name,
                "mode": self._settings.app_mode,
                "total_steps": len(results),
                "ok_steps": sum(1 for item in results if item.ok),
                "error_steps": sum(1 for item in results if not item.ok),
                "run_dir": str(run_dir),
            }
            write_json(run_dir / "final_summary.json", summary)
            return summary
        finally:
            self._save_latest_run(run_dir)
