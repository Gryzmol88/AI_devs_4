"""Podpowiedzi i kandydaci argumentow dla misji pobocznej."""

from __future__ import annotations


def german_butterfly_candidates() -> list[str]:
    """Zwraca kandydatow zwiazanych z podpowiedzia "niemiecki motyl/wihajster".

    Returns:
        Lista wariantow tekstowych do testowania jako argument programu.
    """

    return [
        "Schmetterling",
        "schmetterling",
        "SCHMETTERLING",
        '"Schmetterling"',
        "'Schmetterling'",
        "der_Schmetterling",
        "der Schmetterling",
        "ein Schmetterling",
        "Schluessel",
        "Schlussel",
        "Werkzeug",
        "Werkzeugchen",
        "Wihajster",
        "wihajster",
        "Wihajsterchen",
        "Dingsbums",
        "Dingenskirchen",
        "Dings",
        "Ding",
    ]
