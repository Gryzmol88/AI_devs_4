"""Klient HTTP do analizy treści przez OpenRouter."""

from __future__ import annotations

import time
from typing import Any

import requests

from config import Settings


class OpenRouterClient:
    """Realizuje wywołania modelu na platformie OpenRouter."""

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klient OpenRouter.

        Args:
            settings: Obiekt konfiguracyjny aplikacji.
        """
        self._settings = settings
        self._url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
        self._max_retries = 3

    @staticmethod
    def _empty_facts() -> dict[str, Any]:
        """Zwraca pusty payload faktów zgodny ze schematem raportu."""
        return {
            "cityName": None,
            "cityArea": None,
            "warehousesCount": None,
            "phoneNumber": None,
        }

    def _post_with_retry(
        self, payload: dict[str, Any], headers: dict[str, str]
    ) -> dict[str, Any]:
        """Wysyła zapytanie do OpenRouter z retry dla błędów tymczasowych.

        Args:
            payload: Ładunek JSON do endpointu /chat/completions.
            headers: Nagłówki HTTP żądania.

        Returns:
            Zdeserializowana odpowiedź JSON.

        Raises:
            requests.HTTPError: Gdy błąd nie jest tymczasowy lub wyczerpano retry.
        """
        for attempt in range(1, self._max_retries + 1):
            response = requests.post(
                self._url,
                json=payload,
                headers=headers,
                timeout=self._settings.request_timeout_seconds,
            )
            if response.status_code == 402:
                response.raise_for_status()

            should_retry = response.status_code in {408, 409, 429, 500, 502, 503, 504}
            if not should_retry:
                response.raise_for_status()
                return response.json()

            if attempt == self._max_retries:
                response.raise_for_status()

            time.sleep(0.75 * attempt)
        return {}

    def _parse_facts_from_body(self, body: dict[str, Any]) -> dict[str, Any]:
        """Parsuje payload faktów z odpowiedzi modelu.

        Args:
            body: Surowa odpowiedź JSON z OpenRouter.

        Returns:
            Słownik faktów lub pusty payload, jeśli brak poprawnego content.
        """
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return self._empty_facts()
        message = choices[0].get("message", {})
        if not isinstance(message, dict):
            return self._empty_facts()
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            return self._empty_facts()
        try:
            return requests.models.complexjson.loads(content)
        except ValueError:
            return self._empty_facts()

    def extract_facts(self, text: str) -> dict[str, Any]:
        """Wyciąga fakty docelowe z przekazanego tekstu.

        Args:
            text: Tekst do analizy semantycznej.

        Returns:
            Słownik JSON z polami cityName, cityArea, warehousesCount, phoneNumber
            lub null dla pól nierozpoznanych.
        """
        system_prompt = (
            "Jesteś parserem faktów. Zwróć TYLKO JSON z kluczami: "
            "cityName, cityArea, warehousesCount, phoneNumber. "
            "Dla brakujących wartości użyj null. "
            "Nie dodawaj komentarzy."
        )
        user_prompt = f"Tekst do analizy:\n{text}"

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        payload: dict[str, Any] = {
            "model": self._settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        body = self._post_with_retry(payload=payload, headers=headers)
        return self._parse_facts_from_body(body)

    def extract_facts_from_image_base64(self, image_base64: str, mime_type: str) -> dict[str, Any]:
        """Wyciąga fakty docelowe z obrazu przekazanego jako Base64.

        Args:
            image_base64: Dane obrazu zakodowane w Base64.
            mime_type: Typ MIME obrazu (np. image/png).

        Returns:
            Słownik JSON z polami cityName, cityArea, warehousesCount, phoneNumber
            lub null dla pól nierozpoznanych.
        """
        system_prompt = (
            "Jesteś parserem faktów z obrazu. Odczytaj tylko dane, które występują jawnie. "
            "Zwróć TYLKO JSON z kluczami: cityName, cityArea, warehousesCount, phoneNumber. "
            "Dla brakujących wartości użyj null."
        )

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        payload: dict[str, Any] = {
            "model": self._settings.openrouter_vision_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Wyciągnij dane do raportu radiomonitoring."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            },
                        },
                    ],
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }

        body = self._post_with_retry(payload=payload, headers=headers)
        return self._parse_facts_from_body(body)

    def extract_text_from_image_base64(self, image_base64: str, mime_type: str) -> dict[str, Any]:
        """Odczytuje tekst z obrazu i zwraca go jako JSON.

        Args:
            image_base64: Dane obrazu zakodowane w Base64.
            mime_type: Typ MIME obrazu (np. image/png).

        Returns:
            Slownik z kluczem text (str lub pusty string).
        """
        system_prompt = (
            "Odczytaj tekst widoczny na obrazie. "
            "Zwroc TYLKO JSON z kluczem text. "
            "Jesli tekstu brak, zwroc pusty string."
        )
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        payload: dict[str, Any] = {
            "model": self._settings.openrouter_vision_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Przepisz tekst z obrazu."},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_base64}"
                            },
                        },
                    ],
                },
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        body = self._post_with_retry(payload=payload, headers=headers)
        parsed = self._parse_facts_from_body(body)
        text_value = parsed.get("text")
        if isinstance(text_value, str):
            return {"text": text_value}
        return {"text": ""}

    def extract_warehouses_count(self, text: str) -> dict[str, Any]:
        """Wyciaga tylko liczbe magazynow z przekazanego tekstu.

        Args:
            text: Polaczony material z transkrypcji/OCR/zalacznikow.

        Returns:
            Slownik zawierajacy klucz warehousesCount (int lub null).
        """
        system_prompt = (
            "Jestes parserem jednego pola. "
            "Zwroc TYLKO JSON z kluczem warehousesCount. "
            "Jesli liczba magazynow nie wystepuje wprost, zwroc null. "
            "Nie zgaduj."
        )
        user_prompt = f"Material do analizy:\n{text}"

        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        payload: dict[str, Any] = {
            "model": self._settings.openrouter_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        body = self._post_with_retry(payload=payload, headers=headers)
        parsed = self._parse_facts_from_body(body)
        value = parsed.get("warehousesCount")
        if value is None:
            return {"warehousesCount": None}
        if isinstance(value, int):
            return {"warehousesCount": value}
        as_text = str(value).strip()
        if as_text.isdigit():
            return {"warehousesCount": int(as_text)}
        return {"warehousesCount": None}

    def extract_warehouses_count_from_image_base64(
        self, image_base64: str, mime_type: str, samples: int = 3
    ) -> dict[str, Any]:
        """Wyciaga liczbe magazynow z obrazu i stosuje glosowanie wiekszosciowe.

        Args:
            image_base64: Dane obrazu zakodowane w Base64.
            mime_type: Typ MIME obrazu (np. image/png).
            samples: Liczba prob ekstrakcji do glosowania.

        Returns:
            Slownik zawierajacy warehousesCount oraz debug z prob.
        """
        system_prompt = (
            "Jestes parserem jednego pola z obrazu. "
            "Zwroc TYLKO JSON z kluczem warehousesCount. "
            "Wybierz wartosc AKTUALNA. "
            "Ignoruj wartosci planowane, prognozy i cele. "
            "Jesli brak jednoznacznej liczby aktualnej, zwroc null."
        )
        headers = {
            "Authorization": f"Bearer {self._settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self._settings.openrouter_referer:
            headers["HTTP-Referer"] = self._settings.openrouter_referer
        if self._settings.openrouter_title:
            headers["X-Title"] = self._settings.openrouter_title

        attempts: list[dict[str, Any]] = []
        votes: dict[int, int] = {}
        total_samples = max(1, samples)

        for _ in range(total_samples):
            payload: dict[str, Any] = {
                "model": self._settings.openrouter_vision_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Podaj liczbe magazynow (stan aktualny)."},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                },
                            },
                        ],
                    },
                ],
                "temperature": 0,
                "response_format": {"type": "json_object"},
            }
            body = self._post_with_retry(payload=payload, headers=headers)
            parsed = self._parse_facts_from_body(body)
            value = parsed.get("warehousesCount")
            normalized: int | None = None
            if isinstance(value, int):
                normalized = value
            elif value is not None:
                as_text = str(value).strip()
                if as_text.isdigit():
                    normalized = int(as_text)
            attempts.append({"raw": parsed, "warehousesCount": normalized})
            if normalized is not None:
                votes[normalized] = votes.get(normalized, 0) + 1

        if not votes:
            return {"warehousesCount": None, "attempts": attempts}
        winner = sorted(votes.items(), key=lambda x: x[1], reverse=True)[0][0]
        return {"warehousesCount": winner, "attempts": attempts}
