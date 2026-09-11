"""Niewielkie narzędzia pomocnicze dla agentów."""


def chunked(items: list[str], size: int) -> list[list[str]]:
    """Dzieli listę elementów na partie o zadanym rozmiarze.

    Args:
        items: Lista wejściowa.
        size: Rozmiar pojedynczej partii.

    Returns:
        list[list[str]]: Lista partii.
    """

    if size <= 0:
        return [items]
    return [items[index : index + size] for index in range(0, len(items), size)]

