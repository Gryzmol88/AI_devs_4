"""Orkiestracja rozmowy phonecall z kontrola etapow i zapisem postepu."""

from __future__ import annotations

import base64
import json
import random
from pathlib import Path

import requests

from clients.hub_client import HubClient
from models import DialogState, HubResponse, StepSnapshot
from services.audio_service import AudioService
from services.speech_style_service import SpeechStyleService
from services.transcript_parser import choose_passable_road, parse_operator_text
from utils.logger import log_info


class DialogManager:
    """Zarzadza pelnym przebiegiem rozmowy z operatorem.

    Args:
        hub_client: Klient API centrali zadania.
        audio_service: Serwis konwersji tekst/audio.
        output_dir: Katalog zapisu wynikow posrednich i finalnych.
    """

    def __init__(
        self,
        hub_client: HubClient,
        audio_service: AudioService,
        speech_style: SpeechStyleService,
        output_dir: Path,
    ) -> None:
        """Inicjalizuje manager dialogu i stan poczatkowy."""

        self._hub = hub_client
        self._audio = audio_service
        self._speech_style = speech_style
        self._output_dir = output_dir
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._state = DialogState.INTRO
        self._step = 0
        self._selected_road: str | None = None
        self._asked_roads = False

    def run(self, max_steps: int = 12) -> HubResponse:
        """Wykonuje rozmowe etapami do uzyskania finalnej odpowiedzi.

        Args:
            max_steps: Maksymalna liczba wymian w jednej sesji.

        Returns:
            HubResponse: Ostatnia odpowiedz API po zakonczeniu petli.
        """

        log_info("Start sesji phonecall.")
        start_response = self._hub.start_call()
        self._save_raw("step0_start_response.json", start_response.raw)
        last_response = start_response
        last_inbound_text = ""
        history_lines: list[str] = []

        for _ in range(max_steps):
            self._step += 1
            outbound_base_text = self._next_outbound_text()
            outbound_text = self._speech_style.humanize(
                outbound_base_text,
                self._state,
                last_inbound_text,
                "\n".join(history_lines),
            )
            outbound_audio = self._audio.synthesize_to_base64(outbound_text)
            self._save_step_snapshot(outbound_text=outbound_text, inbound_text=None)
            self._save_text(f"step{self._step}_outbound.txt", outbound_text)
            self._save_audio_mp3(
                filename=f"step{self._step}_outbound.mp3",
                audio_base64=outbound_audio,
            )

            log_info(f"Krok {self._step}: wysylam komunikat w stanie {self._state.value}.")
            try:
                last_response = self._hub.send_audio(outbound_audio)
            except requests.HTTPError as exc:
                self._save_hub_error_audio(exc)
                raise

            inbound_text = self._extract_inbound_text(last_response)
            if last_response.audio_base64:
                self._save_audio_mp3(
                    filename=f"step{self._step}_inbound.mp3",
                    audio_base64=last_response.audio_base64,
                )
            history_lines.append(f"AGENT: {outbound_text}")
            history_lines.append(f"CENTRALA: {inbound_text}")
            self._save_text(f"step{self._step}_history.txt", "\n".join(history_lines))
            last_inbound_text = inbound_text
            self._advance_state(inbound_text)
            self._save_step_snapshot(outbound_text, inbound_text)
            self._save_raw(f"step{self._step}_raw_response.json", last_response.raw)

            if last_response.done or self._state == DialogState.FINISH:
                break

        self._save_raw("final_response.json", last_response.raw)
        self._save_text("final_result.txt", json.dumps(last_response.raw, ensure_ascii=False))
        return last_response

    def _next_outbound_text(self) -> str:
        """Buduje komunikat tekstowy na podstawie aktualnego stanu.

        Returns:
            str: Krotkie polecenie do wypowiedzenia operatorowi.
        """

        if self._state == DialogState.INTRO:
            return random.choice(
                [
                    "Dzien dobry, tu Tymon Gajewski.",
                    "Dzien dobry, z tej strony Tymon Gajewski.",
                    "Tu Tymon Gajewski, dzien dobry.",
                ]
            )

        if self._state == DialogState.ASK_ROADS:
            if not self._asked_roads:
                self._asked_roads = True
                return random.choice(
                    [
                        "Potrzebuje statusu odcinkow RD224, RD472 i RD820, mamy pilny transport.",
                        "Sprawdz mi RD224, RD472 i RD820, potrzebuje przejazdu na szybko.",
                        "Podaj status RD224, RD472 i RD820, jedziemy z pilnym transportem.",
                    ]
                )
            return random.choice(
                [
                    "Ktory odcinek jest teraz przejezdny: RD224, RD472 czy RD820?",
                    "Daj znac, ktora z tras RD224, RD472, RD820 jest teraz drozna.",
                    "Ktora trasa jest wolna, RD224, RD472 czy RD820?",
                ]
            )

        if self._state == DialogState.REQUEST_DISABLE:
            road = self._selected_road or "RD224"
            return random.choice(
                [
                    f"Dobra, wylacz monitoring na {road}, haslo BARBAKAN.",
                    f"Okej, zdejmnij monitoring z {road}, haslo BARBAKAN.",
                    f"To teraz wylacz monitoring na {road}, haslo BARBAKAN.",
                ]
            )

        if self._state == DialogState.ANSWER_QUESTION:
            self._state = DialogState.REQUEST_DISABLE
            return random.choice(
                [
                    "Wieziemy zywnosc do bazy Zygfryda, lokalizacji nie wpisuj do logow.",
                    "To transport zywnosci, bez lokalizacji w logach.",
                    "Jedziemy z zaopatrzeniem, lokalizacja ma nie trafic do logow.",
                ]
            )

        return random.choice(["Dzieki, potwierdzam.", "Dobra, mamy to.", "Super, dzieki."])

    def _extract_inbound_text(self, response: HubResponse) -> str:
        """Odczytuje tekst odpowiedzi operatora z danych audio lub pola tekstowego.

        Args:
            response: Odpowiedz API centrali.

        Returns:
            str: Tekst odpowiedzi operatora.
        """

        if response.audio_base64:
            return self._audio.transcribe_from_base64(response.audio_base64)
        return response.text or ""

    def _advance_state(self, inbound_text: str) -> None:
        """Aktualizuje stan rozmowy na podstawie odpowiedzi operatora.

        Args:
            inbound_text: Tekst odpowiedzi operatora.
        """

        parsed = parse_operator_text(inbound_text)
        if self._state == DialogState.INTRO:
            self._state = DialogState.ASK_ROADS
            return

        if self._state == DialogState.ASK_ROADS:
            self._selected_road = choose_passable_road(parsed.road_status)
            if self._selected_road:
                self._state = DialogState.REQUEST_DISABLE
            return

        if parsed.asks_why_disable:
            self._state = DialogState.ANSWER_QUESTION
            return

        if parsed.confirms_disable:
            self._state = DialogState.FINISH

    def _save_step_snapshot(self, outbound_text: str, inbound_text: str) -> None:
        """Zapisuje podsumowanie kroku dialogu do pliku JSON.

        Args:
            outbound_text: Tekst wyslany przez agenta.
            inbound_text: Tekst odebrany od operatora.
        """

        snapshot = StepSnapshot(
            step=self._step,
            state=self._state,
            outbound_text=outbound_text,
            inbound_text=inbound_text,
            selected_road=self._selected_road,
        )
        path = self._output_dir / f"step{self._step}_analysis.json"
        path.write_text(snapshot.model_dump_json(indent=2, ensure_ascii=False), encoding="utf-8")

    def _save_raw(self, filename: str, data: dict) -> None:
        """Zapisuje surowa odpowiedz JSON do katalogu `output`.

        Args:
            filename: Nazwa pliku wyjsciowego.
            data: Struktura danych do zapisania.
        """

        path = self._output_dir / filename
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _save_text(self, filename: str, content: str) -> None:
        """Zapisuje tresc tekstowa do pliku.

        Args:
            filename: Nazwa pliku docelowego.
            content: Tekst do zapisania.
        """

        path = self._output_dir / filename
        path.write_text(content, encoding="utf-8")

    def _save_hub_error_audio(self, error: requests.HTTPError) -> None:
        """Zapisuje audio z odpowiedzi blednej HUB do pliku diagnostycznego.

        Args:
            error: Wyjatek HTTP zawierajacy obiekt odpowiedzi.
        """

        if error.response is None:
            return
        try:
            payload = error.response.json()
        except ValueError:
            return
        audio_base64 = payload.get("audio")
        if not isinstance(audio_base64, str):
            return
        self._save_text(f"step{self._step}_hub_error_audio_base64.txt", audio_base64)
        self._save_audio_mp3(
            filename=f"step{self._step}_hub_error_audio.mp3",
            audio_base64=audio_base64,
        )

    def _save_audio_mp3(self, filename: str, audio_base64: str) -> None:
        """Zapisuje nagranie audio base64 do pliku MP3.

        Args:
            filename: Nazwa pliku docelowego MP3.
            audio_base64: Dane audio zakodowane base64.
        """

        normalized = audio_base64.strip()
        if "," in normalized and "base64" in normalized[:64]:
            normalized = normalized.split(",", 1)[1].strip()
        padding = len(normalized) % 4
        if padding:
            normalized += "=" * (4 - padding)
        audio_bytes = base64.b64decode(normalized)
        path = self._output_dir / filename
        path.write_bytes(audio_bytes)
        log_info(f"Zapisano audio: {path} ({len(audio_bytes)} bajtow)")
