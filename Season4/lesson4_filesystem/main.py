"""Punkt wejścia programu rozwiązującego zadanie filesystem."""

from src.config import load_settings
from src.runner import FilesystemRunner


def main() -> None:
    """Uruchamia pełny przebieg zadania filesystem.

    Returns:
        None: Funkcja uruchamia runner i drukuje podsumowanie wykonania.
    """

    settings = load_settings()
    print(f"[filesystem] Task: {settings.task_name}")
    print(f"[filesystem] Output base: {settings.output_path}")
    runner = FilesystemRunner(settings)
    result = runner.run()
    print(f"[filesystem] Output run: {runner.last_output_dir}")
    print(f"[filesystem] Finalny wynik: {result}")


if __name__ == "__main__":
    main()

