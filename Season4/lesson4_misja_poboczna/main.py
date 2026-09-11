"""Punkt wejścia narzędzia do eksploracji misji pobocznej lekcji 4."""

from src.config import load_settings
from src.runner import SideMissionRunner


def main() -> None:
    """Uruchamia pełną sekwencję probe'ów dla misji pobocznej.

    Returns:
        None: Funkcja uruchamia runner i wypisuje podsumowanie.
    """

    settings = load_settings()
    print(f"[lesson4_side] Task: {settings.task_name}")
    print(f"[lesson4_side] Mode: {settings.app_mode}")
    print(f"[lesson4_side] Verify URL: {settings.ag3nts_verify_url}")
    print(f"[lesson4_side] Output base: {settings.output_path}")
    runner = SideMissionRunner(settings=settings)
    result = runner.run()
    print(f"[lesson4_side] Output run: {runner.last_output_dir}")
    print(f"[lesson4_side] Final summary: {result}")


if __name__ == "__main__":
    main()
