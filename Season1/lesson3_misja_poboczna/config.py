import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
SEASON1_DIR = BASE_DIR.parent
PROJECT_DIR = SEASON1_DIR.parent


def _load_env_files() -> list[str]:
    """Laduje .env z kilku typowych lokalizacji i zwraca liste trafionych sciezek."""
    candidates = [
        BASE_DIR / ".env",
        SEASON1_DIR / ".env",
        PROJECT_DIR / ".env",
    ]
    loaded: list[str] = []
    for path in candidates:
        if path.exists():
            load_dotenv(path, override=False, encoding="utf-8-sig")
            loaded.append(str(path))
    return loaded


LOADED_DOTENV_FILES = _load_env_files()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
# Misja poboczna ma dzialac na Sonnet 4.6 niezaleznie od globalnego OPENROUTER_MODEL.
OPENROUTER_MODEL = "anthropic/claude-sonnet-4.6"

HUB_API_KEY = os.getenv("HUB_API_KEY", "")
PACKAGES_API_URL = os.getenv("PACKAGES_API_URL", "https://hub.ag3nts.org/api/packages")
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "6"))

HAS_OPENROUTER_KEY = bool(OPENROUTER_API_KEY.strip())
HAS_HUB_KEY = bool(HUB_API_KEY.strip())
