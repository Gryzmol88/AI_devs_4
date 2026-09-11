"""Klient HTTP do komunikacji z endpointem /verify."""

import json
from typing import Any
from urllib.error import HTTPError
from urllib import request

from config import Settings
from models.schemas import VerifyRequest, VerifyResponse


class ApiClientHttpError(Exception):
    """Błąd HTTP zwrócony przez endpoint API.

    Args:
        status_code: Kod HTTP odpowiedzi błędnej.
        reason: Powód błędu HTTP.
        body: Treść odpowiedzi zwrócona przez serwer.
        url: Adres endpointu, do którego wysłano żądanie.
        payload: Payload żądania wysłany do serwera.
    """

    def __init__(
        self,
        status_code: int,
        reason: str,
        body: str,
        url: str,
        payload: dict[str, Any],
    ) -> None:
        """Inicjalizuje wyjątek z pełnym kontekstem odpowiedzi HTTP."""

        self.status_code = status_code
        self.reason = reason
        self.body = body
        self.url = url
        self.payload = payload
        super().__init__(f"HTTP {status_code} {reason}: {body}")


class ApiClient:
    """Obsługuje żądania do API zadania.

    Args:
        settings: Konfiguracja aplikacji.
    """

    def __init__(self, settings: Settings) -> None:
        """Inicjalizuje klienta API.

        Args:
            settings: Konfiguracja aplikacji.
        """

        self._settings = settings

    def call_tool(self, payload: dict[str, Any]) -> VerifyResponse:
        """Wysyła pojedyncze wywołanie narzędzia do endpointu /verify.

        Args:
            payload: Obiekt w polu `answer`.

        Returns:
            Odpowiedź API zmapowana do modelu VerifyResponse.
        """

        body = VerifyRequest(
            apikey=self._settings.aidevs_api_key,
            task=self._settings.aidevs_task,
            answer=payload,
        ).model_dump()

        try:
            raw = self._post_json(self._settings.aidevs_verify_url, body)
        except ApiClientHttpError as exc:
            # Fallback kompatybilności: część endpointów oczekuje action nawet dla prostych wywołań.
            if "action" not in payload and "Missing required field: action." in exc.body:
                retried_payload = {**payload, "action": "get"}
                retried_body = VerifyRequest(
                    apikey=self._settings.aidevs_api_key,
                    task=self._settings.aidevs_task,
                    answer=retried_payload,
                ).model_dump()
                raw = self._post_json(self._settings.aidevs_verify_url, retried_body)
            else:
                raise

        if isinstance(raw, dict):
            return VerifyResponse(**raw)
        return VerifyResponse(data=raw)

    def fetch_json_url(self, url: str) -> Any:
        """Pobiera dowolny dokument JSON z podanego URL.

        Args:
            url: Adres zasobu JSON.

        Returns:
            Zdekodowane dane JSON.
        """

        req = request.Request(url=url, method="GET")
        with request.urlopen(req, timeout=self._settings.request_timeout_seconds) as response:
            content = response.read().decode("utf-8")
            return json.loads(content)

    def _post_json(self, url: str, data: dict[str, Any]) -> Any:
        """Wysyła żądanie POST z JSON i zwraca odpowiedź.

        Args:
            url: Adres endpointu.
            data: Payload do serializacji.

        Returns:
            Dane odpowiedzi po deserializacji JSON.
        """

        payload = json.dumps(data).encode("utf-8")
        req = request.Request(
            url=url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self._settings.request_timeout_seconds) as response:
                content = response.read().decode("utf-8")
                return json.loads(content)
        except HTTPError as exc:
            body = ""
            if exc.fp is not None:
                body = exc.fp.read().decode("utf-8", errors="replace")
            raise ApiClientHttpError(
                status_code=exc.code,
                reason=exc.reason,
                body=body,
                url=url,
                payload=data,
            ) from exc
