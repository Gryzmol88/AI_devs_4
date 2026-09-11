import os

from dotenv import load_dotenv

# Laduje zmienne z pliku .env, aby lokalnie dzialac bez recznego ustawiania
# kazdej wartosci w systemie.
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-5-mini")
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
HUB_API_KEY = os.getenv("HUB_API_KEY", "")
PACKAGES_API_URL = os.getenv("PACKAGES_API_URL", "https://hub.ag3nts.org/api/packages")
MAX_TOOL_ITERATIONS = int(os.getenv("MAX_TOOL_ITERATIONS", "5"))
