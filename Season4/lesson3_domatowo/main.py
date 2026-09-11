"""Punkt wejścia programu rozwiązującego zadanie domatowo."""

from src.config import load_settings
from src.runner import DomatowoRunner


def main() -> None:
    """Uruchamia przebieg całej misji domatowo.

    Returns:
        None: Funkcja uruchamia runner i drukuje podsumowanie wyniku.
    """

    settings = load_settings()
    print(f"[domatowo] Task: {settings.task_name}")
    print(f"[domatowo] Output base: {settings.output_path}")
    runner = DomatowoRunner(settings)
    result = runner.run()
    if runner.last_output_dir is not None:
        print(f"[domatowo] Output run: {runner.last_output_dir}")
    print(f"[domatowo] Finalny wynik: {result}")


if __name__ == "__main__":
    main()
