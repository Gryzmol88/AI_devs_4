"""Serwis odpowiedzialny za generowanie podpisów zamówień."""

from typing import Any

from api_client import ApiClient


class SignatureService:
    """Generuje podpisy przez narzędzie `signatureGenerator`.

    Args:
        api_client: Klient API /verify.
    """

    def __init__(self, api_client: ApiClient) -> None:
        """Inicjalizuje serwis podpisów.

        Args:
            api_client: Klient API /verify.
        """

        self._api_client = api_client

    def generate(self, payload: dict[str, Any]) -> str:
        """Generuje podpis SHA1 na podstawie danych użytkownika.

        Args:
            payload: Dane wymagane przez `signatureGenerator`.

        Returns:
            Wygenerowany podpis jako tekst.
        """

        request_payload = {
            "tool": "signatureGenerator",
            "action": payload.get("action", "generate"),
            **payload,
        }
        response = self._api_client.call_tool(request_payload)
        raw = response.model_dump()

        if isinstance(response.data, dict):
            if "signature" in response.data:
                return str(response.data["signature"])
            if "hash" in response.data:
                return str(response.data["hash"])
        if isinstance(response.data, str):
            return response.data

        if "signature" in raw:
            return str(raw["signature"])
        if "hash" in raw:
            return str(raw["hash"])

        raise ValueError("Nie udało się odczytać podpisu z odpowiedzi signatureGenerator.")
