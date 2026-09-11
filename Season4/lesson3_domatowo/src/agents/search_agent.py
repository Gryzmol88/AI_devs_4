"""Agent deterministyczny odpowiedzialny za kolejność inspekcji pól."""

from __future__ import annotations

from .typing_utils import chunked


class SearchAgent:
    """Dostarcza porcje pól do przeszukiwania w pętli wykonawczej.

    Agent nie komunikuje się bezpośrednio z API. Jego rolą jest utrzymanie
    prostego, przewidywalnego harmonogramu inspekcji.
    """

    def __init__(self, cells: list[str], batch_size: int = 20) -> None:
        """Inicjalizuje agenta z listą pól i wielkością partii.

        Args:
            cells: Lista pól do inspekcji.
            batch_size: Liczba pól zwracanych jednorazowo.
        """

        self._cells = cells
        self._batch_size = batch_size

    def batches(self) -> list[list[str]]:
        """Zwraca listę partii pól do iteracyjnego przetwarzania.

        Returns:
            list[list[str]]: Podzielona lista pól.
        """

        return chunked(self._cells, self._batch_size)

