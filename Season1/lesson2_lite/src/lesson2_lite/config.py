import os
from pathlib import Path


def load_env_file(env_path: Path) -> None:
    """
    Wczytuje zmienne z pliku .env i ustawia tylko te, ktorych jeszcze nie ma
    w srodowisku procesu, aby nie nadpisywac juz przekazanych wartosci.
    """
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def bootstrap_env() -> None:
    """
    Laduje .env najpierw z lesson2_lite, a potem z katalogu glownego projektu,
    aby skrypt dzialal bez dodatkowej konfiguracji sciezek.
    """
    current_dir = Path(__file__).resolve().parents[2]
    root_dir = current_dir.parent
    load_env_file(current_dir / ".env")
    load_env_file(root_dir / ".env")


def get_required_env(name: str) -> str:
    """
    Zwraca wymagana zmienna srodowiskowa i rzuca czytelny blad, jesli jej brak.
    """
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Brak wymaganej zmiennej: {name}")
    return value


def get_hub_api_key() -> str:
    """
    Pobiera klucz do API huba z HUB_API_KEY albo API_KEY.
    """
    return os.getenv("HUB_API_KEY") or get_required_env("API_KEY")

