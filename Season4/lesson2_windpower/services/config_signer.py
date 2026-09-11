"""Podpisywanie punktow konfiguracji kodem unlockCode."""

from __future__ import annotations

import time
from typing import Any

from clients.aidevs_api import AIDevsApiClient
from models.schemas import ConfigPoint


class ConfigSigner:
    """Generuje podpis unlockCode dla kazdego punktu konfiguracji."""

    def __init__(self, api_client: AIDevsApiClient) -> None:
        """Inicjalizuje serwis podpisywania.

        Args:
            api_client: Klient API verify.
        """

        self._api_client = api_client

    def sign(self, config_point: ConfigPoint) -> str:
        """Pobiera unlockCode dla pojedynczego punktu.

        Args:
            config_point: Punkt harmonogramu do podpisania.

        Returns:
            Podpis unlockCode.

        Raises:
            ValueError: Gdy API nie zwroci kodu podpisu.
        """

        answer = {
            "action": "unlockCodeGenerator",
            "startDate": config_point.timestamp.strftime("%Y-%m-%d"),
            "startHour": config_point.timestamp.strftime("%H:00:00"),
            "windMs": config_point.wind_ms,
            "pitchAngle": config_point.pitch_angle,
        }
        self._api_client.call(answer)
        response = self._poll_unlock_result()
        unlock_code = self._extract_unlock_code(response=response)
        if not unlock_code:
            raise ValueError(f"Brak unlockCode dla punktu {config_point.as_payload_key()}.")
        return unlock_code

    def build_configs_payload(self, config_points: list[ConfigPoint]) -> dict[str, dict[str, Any]]:
        """Buduje mape configs do akcji config.

        Args:
            config_points: Lista punktow harmonogramu.

        Returns:
            Slownik zgodny z formatem `configs`.
        """

        configs: dict[str, dict[str, Any]] = {}
        for point in config_points:
            unlock_code = self.sign(config_point=point)
            configs[point.as_payload_key()] = {
                "pitchAngle": point.pitch_angle,
                "turbineMode": point.turbine_mode,
                "unlockCode": unlock_code,
            }
        return configs

    def _poll_unlock_result(self) -> dict[str, Any]:
        """Pobiera wynik unlockCodeGenerator z kolejki getResult.

        Returns:
            Odpowiedz API zawierajaca podpis unlockCode.

        Raises:
            ValueError: Gdy nie udalo sie odebrac poprawnego wyniku.
        """

        for _ in range(20):
            try:
                response = self._api_client.get_result()
            except Exception:  # noqa: BLE001
                time.sleep(0.15)
                continue
            source = response.get("sourceFunction")
            if not isinstance(source, str):
                nested = response.get("result")
                if isinstance(nested, dict):
                    nested_source = nested.get("sourceFunction")
                    if isinstance(nested_source, str):
                        source = nested_source
            if source == "unlockCodeGenerator":
                return response
            time.sleep(0.15)
        raise ValueError("Nie odebrano wyniku unlockCodeGenerator z kolejki getResult.")

    @staticmethod
    def _extract_unlock_code(response: dict[str, Any]) -> str:
        """Wydobywa unlockCode z roznorodnych formatow odpowiedzi API.

        Args:
            response: Odpowiedz API po unlockCodeGenerator.

        Returns:
            Kod podpisu lub pusty string.
        """

        for key in ("unlockCode", "code", "signature", "hash"):
            value = response.get(key)
            if isinstance(value, str) and value:
                return value
        for nested_key in ("result", "data", "message"):
            nested = response.get(nested_key)
            if isinstance(nested, dict):
                nested_code = ConfigSigner._extract_unlock_code(response=nested)
                if nested_code:
                    return nested_code
        return ""
