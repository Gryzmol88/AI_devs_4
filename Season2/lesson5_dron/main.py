"""Punkt wejścia CLI dla sekwencji dwóch agentów w Season 2, lekcja 5.

Skrypt uruchamia:
1) agenta vision do analizy mapy i znalezienia sektora tamy,
2) agenta pilota do sterowania dronem i iteracji z `/verify`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_src_on_path() -> None:
    """Dodaje lokalny katalog `src` do `sys.path` dla prostych importów pakietu."""

    lesson_dir = Path(__file__).resolve().parent
    src_dir = lesson_dir / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def main() -> None:
    """Uruchamia pełną sekwencję i wypisuje końcowy wynik JSON."""

    _ensure_src_on_path()

    import json

    from drone_map_agent.sequence_service import run_full_sequence  # Import lokalny po ustawieniu ścieżki.

    result = run_full_sequence()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
