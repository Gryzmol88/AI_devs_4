"""Serwis odkrywający schemat i dane bazy SQLite przez API."""

from typing import Any

from api_client import ApiClient


class DatabaseDiscoveryService:
    """Dostarcza metody odczytu bazy danych przez narzędzie `database`.

    Args:
        api_client: Klient API /verify.
    """

    def __init__(self, api_client: ApiClient) -> None:
        """Inicjalizuje serwis discovery bazy.

        Args:
            api_client: Klient API /verify.
        """

        self._api_client = api_client

    def show_tables(self) -> Any:
        """Pobiera listę tabel z bazy SQLite.

        Returns:
            Dane odpowiedzi z `show tables`.
        """

        response = self._api_client.call_tool(
            {"tool": "database", "query": "show tables"}
        )
        return response.data if response.data is not None else response.model_dump()

    def select(self, query: str) -> Any:
        """Wykonuje zapytanie SELECT przez narzędzie `database`.

        Args:
            query: Zapytanie SQL typu read-only.

        Returns:
            Dane odpowiedzi dla przekazanego zapytania.
        """

        response = self._api_client.call_tool({"tool": "database", "query": query})
        return response.data if response.data is not None else response.model_dump()

