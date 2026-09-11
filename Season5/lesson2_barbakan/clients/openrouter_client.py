"""Klient do integracji z modelami OpenRouter (LLM/STT/TTS)."""

from __future__ import annotations

import base64
import time
from typing import Any

import requests

from config import Settings
from utils.logger import log_info


class OpenRouterClient:
    """Udostępnia metody pracy z modelami OpenRouter.

    Args:
        settings: Konfiguracja z kluczem API i nazwami modeli.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta OpenRouter."""

        self._settings = settings
        self._headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

    def generate_reply(self, system_prompt: str, user_prompt: str) -> str:
        """Generuje odpowiedź tekstową modelu czatu.

        Args:
            system_prompt: Instrukcja systemowa.
            user_prompt: Treść wejściowa dla modelu.

        Returns:
            str: Wygenerowana odpowiedź tekstowa.
        """

        payload = {
            "model": self._settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
        }
        data = self._post_json("/chat/completions", payload)
        return (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

    def text_to_speech(self, text: str) -> str:
        """Konwertuje tekst na dźwięk i zwraca base64.

        Args:
            text: Tekst do syntezy mowy.

        Returns:
            str: Zawartość pliku audio zakodowana base64.
        """

        models = [self._settings.openrouter_tts_model]
        fallback_raw = self._settings.openrouter_tts_fallback_models.strip()
        if fallback_raw:
            fallback_models = [m.strip() for m in fallback_raw.split(",") if m.strip()]
            models.extend(fallback_models)

        last_error: Exception | None = None
        for model in models:
            for attempt in range(1, self._settings.openrouter_tts_max_retries + 1):
                response_format = self._get_tts_response_format(model)
                payload = {
                    "model": model,
                    "input": text,
                    "response_format": response_format,
                    "voice": self._settings.openrouter_tts_voice,
                    "speed": self._settings.openrouter_tts_speed,
                }
                log_info(
                    f"TTS model={model}, format={response_format}, proba={attempt}"
                )
                try:
                    audio_bytes = self._post_binary("/audio/speech", payload)
                    return base64.b64encode(audio_bytes).decode("utf-8")
                except requests.HTTPError as exc:
                    last_error = exc
                    status_code = exc.response.status_code if exc.response is not None else 0
                    is_retryable = status_code >= 500
                    if not is_retryable:
                        break
                    if attempt < self._settings.openrouter_tts_max_retries:
                        sleep_seconds = (
                            self._settings.openrouter_tts_retry_backoff_seconds * attempt
                        )
                        time.sleep(sleep_seconds)
            if last_error is None:
                continue
            status_code = last_error.response.status_code if last_error.response is not None else 0
            if status_code < 500:
                raise last_error

        if last_error is not None:
            raise last_error
        raise RuntimeError("Nie udalo sie wygenerowac audio TTS.")

    def speech_to_text(self, audio_base64: str) -> str:
        """Konwertuje dźwięk zakodowany base64 na tekst.

        Args:
            audio_base64: Dane audio MP3 zakodowane base64.

        Returns:
            str: Rozpoznany tekst.
        """

        payload = {
            "model": self._settings.openrouter_stt_model,
            "input_audio": {
                "data": audio_base64,
                "format": self._settings.openrouter_stt_audio_format,
            },
            "language": self._settings.openrouter_stt_language,
        }
        data = self._post_json("/audio/transcriptions", payload)
        return str(data.get("text", "")).strip()

    def _get_tts_response_format(self, model: str) -> str:
        """Zwraca format audio TTS dopasowany do wybranego modelu.

        Args:
            model: Nazwa modelu TTS.

        Returns:
            str: Format odpowiedzi audio dla modelu.
        """

        normalized = model.lower()
        if "gemini" in normalized:
            return "pcm"
        return self._settings.openrouter_tts_audio_format

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Wysyła żądanie JSON do OpenRouter i zwraca odpowiedź.

        Args:
            path: Ścieżka endpointu API.
            payload: Dane JSON do wysłania.

        Returns:
            dict[str, Any]: Odpowiedź endpointu jako słownik.

        Raises:
            requests.HTTPError: Gdy OpenRouter zwróci błąd HTTP.
        """

        response = requests.post(
            f"{self._settings.openrouter_base_url}{path}",
            headers=self._headers,
            json=payload,
            timeout=self._settings.request_timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text[:1000]}",
                response=response,
            ) from exc
        return response.json()

    def _post_binary(self, path: str, payload: dict[str, Any]) -> bytes:
        """Wysyła żądanie JSON i zwraca odpowiedź binarną.

        Args:
            path: Ścieżka endpointu API.
            payload: Dane JSON do wysłania.

        Returns:
            bytes: Surowe bajty odpowiedzi, np. MP3.

        Raises:
            requests.HTTPError: Gdy OpenRouter zwróci błąd HTTP.
        """

        response = requests.post(
            f"{self._settings.openrouter_base_url}{path}",
            headers=self._headers,
            json=payload,
            timeout=self._settings.request_timeout,
        )
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise requests.HTTPError(
                f"{exc}. Response body: {response.text[:1000]}",
                response=response,
            ) from exc
        return response.content
