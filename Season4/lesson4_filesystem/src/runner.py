"""Orkiestracja etapów rozwiązania zadania filesystem."""

from __future__ import annotations

import io
import json
import re
import zipfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

import requests

from .builder import build_fs_actions
from .config import AppSettings
from .deterministic_extractor import DeterministicNotesExtractor
from .io_utils import create_run_output_dir, write_json, write_text
from .models import ExtractedKnowledge, NormalizedKnowledge
from .normalizer import normalize_knowledge, to_slug
from .openrouter_client import OpenRouterClient
from .parser import NotesParser
from .validator import validate_before_send
from .verify_client import Ag3ntsVerifyClient


class FilesystemRunner:
    """Realizuje pełny workflow budowy struktury plików dla zadania."""

    def __init__(self, settings: AppSettings) -> None:
        """Inicjalizuje runner i zależności aplikacji.

        Args:
            settings: Obiekt konfiguracji aplikacji.
        """

        self._settings = settings
        self._verify_client = Ag3ntsVerifyClient(settings)
        self._llm_client = OpenRouterClient(settings)
        self._parser = NotesParser(self._llm_client, settings.prompt_extract_path)
        self._deterministic_extractor = DeterministicNotesExtractor()
        self.last_output_dir: Path | None = None

    def _download_notes_archive(self) -> bytes:
        """Pobiera archiwum ZIP z notatkami Natana.

        Returns:
            bytes: Surowa zawartość pliku ZIP.

        Raises:
            RuntimeError: Gdy pobieranie nie powiedzie się.
        """

        try:
            response = requests.get(
                self._settings.natan_notes_url,
                timeout=self._settings.request_timeout_seconds,
            )
            response.raise_for_status()
            return response.content
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            body = exc.response.text if exc.response is not None else ""
            raise RuntimeError(
                f"Blad HTTP pobierania notatek: status={status}, body={body}"
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Blad pobierania notatek: {exc}") from exc

    def _extract_texts_from_zip(self, archive_bytes: bytes) -> str:
        """Rozpakowuje ZIP i scala tekst wszystkich plików do jednego dokumentu.

        Args:
            archive_bytes: Surowa zawartość archiwum ZIP.

        Returns:
            str: Połączona treść plików tekstowych.
        """

        chunks: list[str] = []
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            file_names = sorted(archive.namelist())
            for file_name in file_names:
                if file_name.endswith("/"):
                    continue
                with archive.open(file_name, "r") as file_stream:
                    raw_data = file_stream.read()
                text = raw_data.decode("utf-8", errors="ignore")
                chunks.append(f"\n\n### FILE: {file_name}\n{text}")
        return "".join(chunks).strip()

    def _save_action_preview(
        self, output_dir: Path, actions: list[dict[str, Any]]
    ) -> None:
        """Zapisuje podgląd akcji przygotowanych do wysłania.

        Args:
            output_dir: Katalog wynikowy bieżącego uruchomienia.
            actions: Lista payloadów akcji.

        Returns:
            None: Funkcja zapisuje podgląd do pliku JSON.
        """

        write_json(output_dir / "step4_actions.json", actions)

    def _save_latest_symlink_file(self, run_dir: Path) -> None:
        """Aktualizuje plik wskazujący katalog ostatniego uruchomienia.

        Args:
            run_dir: Katalog artefaktów bieżącego przebiegu.

        Returns:
            None: Funkcja zapisuje plik tekstowy z absolutną ścieżką.
        """

        write_text(self._settings.output_path / "latest_run.txt", str(run_dir))

    def _extract_verify_error_payload(self, error: RuntimeError) -> dict[str, Any] | None:
        """Próbuje wyciągnąć JSON błędu verify z treści wyjątku.

        Args:
            error: Wyjątek zgłoszony przez klienta verify.

        Returns:
            dict[str, Any] | None: Payload błędu lub `None` gdy brak poprawnego JSON.
        """

        text = str(error)
        marker = "body="
        marker_index = text.find(marker)
        if marker_index == -1:
            return None
        raw_body = text[marker_index + len(marker) :].strip()
        if not raw_body:
            return None
        try:
            return json.loads(raw_body)
        except json.JSONDecodeError:
            return None

    def _extract_json_from_text(self, text: str) -> dict[str, Any] | None:
        """Próbuje wyciągnąć obiekt JSON z dowolnego tekstu.

        Args:
            text: Tekst wejściowy potencjalnie zawierający JSON.

        Returns:
            dict[str, Any] | None: Obiekt JSON lub `None`, gdy parsowanie się nie powiedzie.
        """

        candidate = text.strip()
        if not candidate:
            return None
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return None
            try:
                parsed = json.loads(candidate[start : end + 1])
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                return None

    def _fill_missing_people(
        self,
        raw_notes: str,
        normalized: NormalizedKnowledge,
        run_dir: Path,
    ) -> None:
        """Uzupełnia brakujące przypisania osoby do miasta.

        Mechanizm najpierw próbuje uzupełnić dane przez LLM, a jeśli to się nie
        powiedzie, stosuje bezpieczny fallback z nazwą techniczną opartą o miasto.

        Args:
            raw_notes: Surowa treść notatek.
            normalized: Znormalizowana wiedza modyfikowana in-place.
            run_dir: Katalog output bieżącego uruchomienia.

        Returns:
            None: Funkcja aktualizuje `normalized.person_to_city`.
        """

        covered_cities = set(normalized.person_to_city.values())
        missing_cities = sorted(
            city for city in normalized.city_needs.keys() if city not in covered_cities
        )
        if not missing_cities:
            return

        print(
            f"[filesystem] Wykryto brak osoby dla miast: {', '.join(missing_cities)}. Uruchamiam uzupełnienie."
        )
        write_json(run_dir / "step4_missing_people_before.json", {"cities": missing_cities})

        llm_payload = {
            "missing_cities": missing_cities,
            "people": [],
        }
        try:
            system_prompt = (
                "Uzupełniasz brakujące osoby odpowiedzialne za handel.\n"
                "Masz zwrócić wyłącznie JSON w formacie:\n"
                '{"people":[{"full_name":"Imie Nazwisko","city_slug":"slug_miasta"}]}\n'
                "Zasady:\n"
                "- Jedna osoba na każde miasto z listy missing_cities.\n"
                "- Użyj danych z notatek i inferencji (np. imię+nazwisko z kontekstu), nie zostawiaj pustych.\n"
                "- full_name: 1-2 wyrazy ASCII."
            )
            user_prompt = (
                f"MISSING_CITIES={missing_cities}\n\n"
                f"NOTATKI:\n{raw_notes}"
            )
            response = self._llm_client.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "people": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "full_name": {"type": "string"},
                                    "city_slug": {"type": "string"},
                                },
                                "required": ["full_name", "city_slug"],
                            },
                        }
                    },
                    "required": ["people"],
                },
            )
            llm_payload = response if isinstance(response, dict) else llm_payload
        except Exception as exc:  # noqa: BLE001
            write_json(
                run_dir / "step4_missing_people_llm_error.json",
                {"error": str(exc)},
            )

        write_json(run_dir / "step4_missing_people_llm.json", llm_payload)

        assigned_cities: set[str] = set()
        existing_people = set(normalized.person_to_city.keys())
        for item in llm_payload.get("people", []):
            if not isinstance(item, dict):
                continue
            full_name = str(item.get("full_name", "")).strip()
            city_slug = to_slug(str(item.get("city_slug", "")).strip())
            if city_slug not in missing_cities or not full_name:
                continue
            person_slug = to_slug(full_name)
            if person_slug in existing_people:
                person_slug = f"{person_slug}_{city_slug}"[:20]
            normalized.person_to_city[person_slug] = city_slug
            normalized.person_display_name[person_slug] = full_name
            existing_people.add(person_slug)
            assigned_cities.add(city_slug)

        remaining = [city for city in missing_cities if city not in assigned_cities]
        for city_slug in remaining:
            # Fallback techniczny gwarantujący 1 plik osoby na każde miasto.
            base_name = f"{city_slug}_opiekun"[:20]
            person_slug = re.sub(r"[^a-z0-9_]+", "_", base_name).strip("_") or city_slug
            while person_slug in existing_people:
                person_slug = f"{person_slug[:17]}_x"
            normalized.person_to_city[person_slug] = city_slug
            normalized.person_display_name[person_slug] = person_slug.replace("_", " ").title()
            existing_people.add(person_slug)

        write_json(
            run_dir / "step4_missing_people_after.json",
            normalized.model_dump(),
        )

    def _apply_unexpected_goods_fix(
        self,
        normalized: NormalizedKnowledge,
        error_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Usuwa nieoczekiwane towary wskazane przez verify dla konkretnego miasta.

        Args:
            normalized: Aktualny stan znormalizowanej wiedzy.
            error_payload: Payload błędu zwrócony przez API verify.

        Returns:
            dict[str, Any] | None: Raport naprawy lub `None` gdy naprawa nie jest możliwa.
        """

        if int(error_payload.get("code", 0)) != -807:
            return None

        city_slug = str(error_payload.get("city", "")).strip()
        unexpected = error_payload.get("unexpected_goods", [])
        if not city_slug or not isinstance(unexpected, list):
            return None
        if city_slug not in normalized.city_needs:
            return None

        removed: list[str] = []
        for item in unexpected:
            item_slug = str(item).strip()
            if not item_slug:
                continue
            if item_slug in normalized.city_needs[city_slug]:
                del normalized.city_needs[city_slug][item_slug]
                removed.append(item_slug)

        if not removed:
            return None

        return {
            "code": -807,
            "city": city_slug,
            "removed_goods": removed,
        }

    def _find_best_amount_for_missing_good(
        self,
        city_slug: str,
        missing_good: str,
        source_city_needs: dict[str, dict[str, int]],
        normalized: NormalizedKnowledge,
    ) -> int:
        """Wyznacza ilość towaru brakującego w mieście na podstawie danych źródłowych.

        Args:
            city_slug: Miasto zgłoszone przez verify.
            missing_good: Brakujący towar zgłoszony przez verify.
            source_city_needs: Migawka potrzeb miast przed auto-naprawami.
            normalized: Aktualny stan znormalizowanych danych.

        Returns:
            int: Oszacowana ilość brakującego towaru.
        """

        candidates = source_city_needs.get(city_slug, {})
        best_score = -1.0
        best_amount: int | None = None
        for item, amount in candidates.items():
            score = SequenceMatcher(None, item, missing_good).ratio()
            if score > best_score:
                best_score = score
                best_amount = amount
        if best_amount is not None and best_score >= 0.45:
            return int(best_amount)

        # Fallback 2: podobny towar z bieżącego miasta po wcześniejszych poprawkach.
        current = normalized.city_needs.get(city_slug, {})
        for item, amount in current.items():
            score = SequenceMatcher(None, item, missing_good).ratio()
            if score >= 0.60:
                return int(amount)

        # Ostatecznie bezpieczna ilość minimalna.
        return 1

    def _apply_missing_goods_fix(
        self,
        normalized: NormalizedKnowledge,
        error_payload: dict[str, Any],
        source_city_needs: dict[str, dict[str, int]],
    ) -> dict[str, Any] | None:
        """Uzupełnia brakujące towary wskazane przez verify dla konkretnego miasta.

        Args:
            normalized: Aktualny stan znormalizowanej wiedzy.
            error_payload: Payload błędu zwrócony przez API verify.
            source_city_needs: Migawka potrzeb miast przed auto-naprawami.

        Returns:
            dict[str, Any] | None: Raport naprawy lub `None` gdy naprawa nie jest możliwa.
        """

        if int(error_payload.get("code", 0)) != -806:
            return None

        city_slug = str(error_payload.get("city", "")).strip()
        missing_goods = error_payload.get("missing_goods", [])
        if not city_slug or not isinstance(missing_goods, list):
            return None
        if city_slug not in normalized.city_needs:
            return None

        added: dict[str, int] = {}
        for item in missing_goods:
            item_slug = str(item).strip()
            if not item_slug:
                continue
            if item_slug in normalized.city_needs[city_slug]:
                continue
            amount = self._find_best_amount_for_missing_good(
                city_slug=city_slug,
                missing_good=item_slug,
                source_city_needs=source_city_needs,
                normalized=normalized,
            )
            normalized.city_needs[city_slug][item_slug] = amount
            added[item_slug] = amount

        if not added:
            return None

        return {"code": -806, "city": city_slug, "added_goods": added}

    def _apply_mismatches_fix(
        self,
        normalized: NormalizedKnowledge,
        error_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Koryguje ilości towarów na podstawie błędu `-804`.

        Args:
            normalized: Aktualny stan znormalizowanych danych.
            error_payload: Payload błędu zwrócony przez verify.

        Returns:
            dict[str, Any] | None: Raport zmian lub `None`, gdy naprawa nie jest możliwa.
        """

        if int(error_payload.get("code", 0)) != -804:
            return None

        city_slug = str(error_payload.get("city", "")).strip()
        mismatches = error_payload.get("mismatches", {})
        if not city_slug or not isinstance(mismatches, dict):
            return None
        if city_slug not in normalized.city_needs:
            return None

        corrected: dict[str, dict[str, int]] = {}
        for item_slug, mismatch in mismatches.items():
            if not isinstance(mismatch, dict):
                continue
            expected = mismatch.get("expected")
            if not isinstance(expected, int):
                continue
            current = normalized.city_needs[city_slug].get(item_slug)
            normalized.city_needs[city_slug][item_slug] = expected
            corrected[item_slug] = {"from": int(current or 0), "to": expected}

        if not corrected:
            return None
        return {"code": -804, "city": city_slug, "corrected": corrected}

    def run(self) -> dict[str, Any]:
        """Uruchamia cały proces rozwiązania zadania filesystem.

        Returns:
            dict[str, Any]: Odpowiedź API po akcji `done`.

        Efekty uboczne:
            Wysyła operacje do API `/verify/` oraz zapisuje artefakty do `output`.
        """

        self._settings.output_path.mkdir(parents=True, exist_ok=True)
        run_dir = create_run_output_dir(self._settings.output_path)
        self.last_output_dir = run_dir

        try:
            write_json(
                run_dir / "step0_run_metadata.json",
                {"run_id": run_dir.name, "task": self._settings.task_name},
            )

            print("[filesystem] Krok 1/8: pobieram help z API")
            help_response = self._verify_client.help()
            write_json(run_dir / "step1_help.json", help_response)

            print("[filesystem] Krok 2/8: pobieram i rozpakowuję notatki")
            archive_bytes = self._download_notes_archive()
            raw_notes = self._extract_texts_from_zip(archive_bytes)
            write_text(run_dir / "step2_raw_notes.txt", raw_notes)

            print("[filesystem] Krok 3/8: ekstrakcja deterministyczna z notatek")
            extracted: ExtractedKnowledge = self._deterministic_extractor.extract(raw_notes)
            write_json(run_dir / "step3_extracted.json", extracted.model_dump())
            if not extracted.cities or not extracted.people:
                raise RuntimeError(
                    "Ekstrakcja deterministyczna zwróciła niekompletne dane. "
                    "Sprawdź step3_extracted.json."
                )

            print("[filesystem] Krok 4/8: normalizacja i walidacja danych")
            normalized = normalize_knowledge(extracted)
            self._fill_missing_people(raw_notes=raw_notes, normalized=normalized, run_dir=run_dir)
            validate_before_send(normalized)
            write_json(run_dir / "step4_normalized.json", normalized.model_dump())
            source_city_needs = {
                city: dict(needs) for city, needs in normalized.city_needs.items()
            }

            print("[filesystem] Krok 5/8: buduję listę akcji filesystem")
            actions = build_fs_actions(normalized)
            action_payload = [action.to_payload() for action in actions]
            self._save_action_preview(run_dir, action_payload)

            if self._settings.reset_filesystem_first:
                print("[filesystem] Krok 6/8: resetuję zdalny filesystem")
                reset_response = self._verify_client.reset()
                write_json(run_dir / "step5_reset.json", reset_response)
            else:
                print("[filesystem] Krok 6/8: pomijam reset filesystemu")

            print("[filesystem] Krok 7/8: wysyłam operacje tworzące strukturę")
            apply_response = self._verify_client.apply_actions(
                actions=actions,
                use_batch=self._settings.use_batch_mode,
            )
            write_json(run_dir / "step6_apply.json", apply_response)

            print("[filesystem] Krok 8/8: wysyłam done")
            max_done_attempts = 3
            final_response: dict[str, Any] | None = None
            for attempt in range(1, max_done_attempts + 1):
                try:
                    final_response = self._verify_client.done()
                    if attempt > 1:
                        print(
                            f"[filesystem] done OK po auto-naprawie, próba {attempt}/{max_done_attempts}"
                        )
                    break
                except RuntimeError as exc:
                    error_payload = self._extract_verify_error_payload(exc)
                    write_json(
                        run_dir / f"step7_done_error_attempt{attempt}.json",
                        {
                            "exception": str(exc),
                            "payload": error_payload,
                        },
                    )
                    fix_report = (
                        self._apply_unexpected_goods_fix(normalized, error_payload)
                        if error_payload is not None
                        else None
                    )
                    if fix_report is None and error_payload is not None:
                        fix_report = self._apply_missing_goods_fix(
                            normalized=normalized,
                            error_payload=error_payload,
                            source_city_needs=source_city_needs,
                        )
                    if fix_report is None and error_payload is not None:
                        fix_report = self._apply_mismatches_fix(
                            normalized=normalized,
                            error_payload=error_payload,
                        )
                    if fix_report is None or attempt == max_done_attempts:
                        raise

                    print(
                        f"[filesystem] done zwrócił {fix_report.get('code')}, wykonuję auto-naprawę i ponawiam reset+apply"
                    )
                    write_json(run_dir / f"step7_fix_attempt{attempt}.json", fix_report)
                    validate_before_send(normalized)
                    write_json(
                        run_dir / f"step7_normalized_attempt{attempt}.json",
                        normalized.model_dump(),
                    )

                    retry_actions = build_fs_actions(normalized)
                    retry_payload = [action.to_payload() for action in retry_actions]
                    write_json(
                        run_dir / f"step7_actions_attempt{attempt}.json",
                        retry_payload,
                    )

                    if self._settings.reset_filesystem_first:
                        retry_reset = self._verify_client.reset()
                        write_json(
                            run_dir / f"step7_reset_attempt{attempt}.json",
                            retry_reset,
                        )

                    retry_apply = self._verify_client.apply_actions(
                        actions=retry_actions,
                        use_batch=self._settings.use_batch_mode,
                    )
                    write_json(
                        run_dir / f"step7_apply_attempt{attempt}.json",
                        retry_apply,
                    )

            if final_response is None:
                raise RuntimeError("Nie udało się uzyskać poprawnej odpowiedzi done.")
            write_json(run_dir / "final_result.json", final_response)
            return final_response
        except Exception as exc:  # noqa: BLE001
            write_json(
                run_dir / "error_trace.json",
                {"error": str(exc), "run_id": run_dir.name},
            )
            raise
        finally:
            self._save_latest_symlink_file(run_dir)
