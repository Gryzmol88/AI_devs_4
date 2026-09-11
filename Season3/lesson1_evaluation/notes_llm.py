"""Klasyfikacja notatek operatora z użyciem OpenRouter i prostego cache."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Literal
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import Settings
from models import NoteAssessment


def _extract_json_block(text: str) -> str:
    """Wyciąga blok JSON (obiekt lub tablicę) z odpowiedzi modelu.

    Args:
        text: Surowa odpowiedź modelu.

    Returns:
        Wycięty fragment JSON.

    Raises:
        ValueError: Gdy w odpowiedzi nie znaleziono bloku JSON.
    """

    match = re.search(r"(\{.*\}|\[.*\])", text, flags=re.DOTALL)
    if not match:
        raise ValueError("Nie znaleziono bloku JSON w odpowiedzi modelu.")
    return match.group(1)


def _heuristic_stance(note: str) -> Literal["ok", "anomaly", "uncertain"]:
    """Stosuje tanią heurystykę klasyfikacji notatki, by ograniczyć użycie modelu.

    Args:
        note: Tekst notatki operatora.

    Returns:
        Jedną z wartości: ok, anomaly, uncertain.
    """

    normalized = note.strip().lower()

    # Najpierw wykrywamy negacje, aby nie oznaczać jako anomaly zdań typu:
    # "no sign of abnormal activity" lub "nothing suggests a fault condition".
    negative_context_patterns = [
        r"\bno sign of abnormal\b",
        r"\bno abnormal activity\b",
        r"\bnothing suggests a fault\b",
        r"\bno warning signs\b",
        r"\bno deviations? to flag\b",
        r"\bwithout (issues|errors|faults)\b",
        r"\bno (issues|errors|faults|problems)\b",
        r"\bno anomaly\b",
    ]
    if any(re.search(pattern, normalized) for pattern in negative_context_patterns):
        return "ok"

    # Najpierw wykrywamy charakterystyczne frazy anomalii.
    anomaly_starts = [
        "the latest behavior is concerning",
        "these readings look suspicious",
        "this state looks unstable",
        "the report does not look healthy",
        "this is not the pattern i expected",
        "i am not comfortable with this result",
        "the current result seems unreliable",
        "something is clearly off",
        "i can see a clear irregularity",
        "i am seeing an unexpected pattern",
        "there is a visible anomaly here",
        "the numbers feel inconsistent",
        "the signal profile looks unusual",
        "the output quality is doubtful",
        "the situation requires attention",
        "this check did not look right",
        "this report raises serious doubts",
        "this run shows questionable behavior",
    ]
    if any(normalized.startswith(marker) for marker in anomaly_starts):
        return "anomaly"

    # Dodatkowe mocne sygnały anomalii.
    strong_anomaly_patterns = [
        r"\bfound (an )?error\b",
        r"\bdetected (an )?error\b",
        r"\bdetected (an )?anomaly\b",
        r"\bout of range\b",
        r"\bcritical (issue|fault|error)\b",
        r"\bfault detected\b",
        r"\berror detected\b",
        r"\balarm triggered\b",
        r"\brequires (maintenance|intervention)\b",
    ]
    if any(re.search(pattern, normalized) for pattern in strong_anomaly_patterns):
        return "anomaly"

    ok_markers = [
        "stable",
        "within expected range",
        "all good",
        "looks good",
        "safe operating zone",
        "normal operation",
        "everything checks out",
        "status stays green",
        "approved as normal",
        "routine observation",
        "all control checks passed cleanly",
        "operating envelope is respected",
        "normal patterns",
        "system response remains predictable",
    ]
    if any(marker in normalized for marker in ok_markers):
        return "ok"

    return "uncertain"


class OpenRouterNotesClassifier:
    """Klasyfikuje notatki operatora do ok/anomaly/uncertain z cache.

    Klasa wykonuje:
    1) klasyfikację heurystyczną oczywistych przypadków,
    2) paczkowane zapytania do OpenRouter dla niejednoznacznych notatek,
    3) trwały zapis cache w katalogu output.
    """

    def __init__(self, settings: Settings, cache_path: Path):
        """Inicjalizuje klasyfikator konfiguracją i ścieżką cache.

        Args:
            settings: Ustawienia aplikacji z danymi do OpenRouter.
            cache_path: Ścieżka pliku JSON używanego jako cache klasyfikacji.
        """

        self.settings = settings
        self.cache_path = cache_path
        self.cache: Dict[str, Dict[str, object]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, object]]:
        """Wczytuje cache z dysku.

        Returns:
            Mapowanie note -> zserializowany słownik NoteAssessment.
        """

        if not self.cache_path.exists():
            return {}
        with self.cache_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {}

    def _save_cache(self) -> None:
        """Zapisuje bieżący cache na dysk."""
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as file:
            json.dump(self.cache, file, ensure_ascii=False, indent=2)

    def classify_unique_notes(self, notes: Iterable[str]) -> Dict[str, NoteAssessment]:
        """Klasyfikuje każdą unikalną notatkę heurystyką i fallbackiem do LLM.

        Args:
            notes: Iterowalna kolekcja unikalnych notatek.

        Returns:
            Mapowanie note -> NoteAssessment.
        """

        unique_notes = sorted({note for note in notes})
        results: Dict[str, NoteAssessment] = {}
        notes_for_llm: List[str] = []

        for note in unique_notes:
            cached = self.cache.get(note)
            if cached:
                results[note] = NoteAssessment.model_validate(cached)
                continue
            stance = _heuristic_stance(note)
            if stance != "uncertain":
                assessment = NoteAssessment(note=note, stance=stance, confidence=0.8, source="heuristic")
                results[note] = assessment
                self.cache[note] = assessment.model_dump()
            else:
                notes_for_llm.append(note)

        if notes_for_llm:
            llm_results = self._classify_with_llm(notes_for_llm)
            results.update(llm_results)
            for note, assessment in llm_results.items():
                self.cache[note] = assessment.model_dump()

        self._save_cache()
        return results

    def _classify_with_llm(self, notes: List[str]) -> Dict[str, NoteAssessment]:
        """Klasyfikuje niejednoznaczne notatki przez OpenRouter w paczkach.

        Args:
            notes: Notatki wymagające klasyfikacji przez model.

        Returns:
            Mapowanie note -> NoteAssessment.
        """

        assessments: Dict[str, NoteAssessment] = {}
        batch_size = max(1, self.settings.llm_batch_size)

        for start in range(0, len(notes), batch_size):
            batch = notes[start : start + batch_size]
            batch_assessments = self._classify_batch(batch)
            assessments.update(batch_assessments)

        return assessments

    def _classify_batch(self, notes_batch: List[str]) -> Dict[str, NoteAssessment]:
        """Wysyła jedną paczkę do OpenRouter i parsuje wynik.

        Args:
            notes_batch: Lista tekstów notatek.

        Returns:
            Mapowanie note -> NoteAssessment dla danej paczki.
        """

        instructions = (
            "Sklasyfikuj postawę każdej notatki operatora.\n"
            "Dozwolone etykiety: ok, anomaly, uncertain.\n"
            "Zwróć WYŁĄCZNIE obiekt JSON z kluczem 'items'.\n"
            "Każdy element: {\"id\": number, \"stance\": \"ok|anomaly|uncertain\", \"confidence\": 0..1}.\n"
            "Nie dodawaj wyjaśnień."
        )
        numbered = [{"id": idx, "note": note} for idx, note in enumerate(notes_batch)]
        user_payload = json.dumps({"items": numbered}, ensure_ascii=False)

        request_payload = {
            "model": self.settings.openrouter_model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": instructions},
                {"role": "user", "content": user_payload},
            ],
        }
        request_bytes = json.dumps(request_payload).encode("utf-8")
        endpoint = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"

        request = Request(
            endpoint,
            data=request_bytes,
            headers={
                "Authorization": f"Bearer {self.settings.openrouter_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.settings.llm_timeout_seconds) as response:  # nosec: B310
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {
                note: NoteAssessment(note=note, stance="uncertain", confidence=0.0, source="llm")
                for note in notes_batch
            }

        model_text = response_payload["choices"][0]["message"]["content"]
        try:
            structured = json.loads(_extract_json_block(model_text))
            items = structured.get("items", [])
        except (json.JSONDecodeError, KeyError, ValueError):
            items = []

        by_id: Dict[int, Dict[str, object]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            if not isinstance(item_id, int):
                continue
            by_id[item_id] = item

        results: Dict[str, NoteAssessment] = {}
        for idx, note in enumerate(notes_batch):
            raw = by_id.get(idx, {})
            raw_stance = raw.get("stance", "uncertain")
            stance = raw_stance if raw_stance in {"ok", "anomaly", "uncertain"} else "uncertain"
            confidence_raw = raw.get("confidence", 0.0)
            confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
            confidence = max(0.0, min(1.0, confidence))
            results[note] = NoteAssessment(note=note, stance=stance, confidence=confidence, source="llm")

        return results
