import json
import time
from collections import defaultdict
from pathlib import Path
from string import Template

import requests
from openai import OpenAI

from settings import Settings

ALLOWED_TAGS = [
    "IT",
    "transport",
    "edukacja",
    "medycyna",
    "praca z ludźmi",
    "praca z pojazdami",
    "praca fizyczna",
]
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 3
DEFAULT_BATCH_SIZE = 80
BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
TAG_JOBS_DEVELOPER_PROMPT_PATH = PROMPTS_DIR / "tag_jobs_developer.md"
TAG_JOBS_USER_PROMPT_PATH = PROMPTS_DIR / "tag_jobs_user.md"
TAG_DESCRIPTIONS = {
    "IT": "praca informatyczna, programowanie, administracja systemami",
    "transport": "logistyka, przewóz, spedycja, dostawy, kolej",
    "edukacja": "nauczanie, szkolenia",
    "medycyna": "opieka zdrowotna, leczenie",
    "praca z ludźmi": "obsługa klienta, HR, sprzedaż, usługi społeczne",
    "praca z pojazdami": "kierowcy, mechanicy, operatorzy pojazdów",
    "praca fizyczna": "produkcja, magazyn, budowa, prace manualne",
}


def _get_openrouter_client() -> OpenAI:
    """Tworzy klienta OpenAI skonfigurowanego pod endpoint OpenRouter."""
    settings = Settings()
    return OpenAI(api_key=settings.OPENROUTER_API_KEY, base_url=OPENROUTER_BASE_URL)


def _build_schema() -> dict:
    """Buduje schemat JSON Schema dla odpowiedzi Structured Output.

    Oczekiwany format to obiekt z listą `items`, gdzie każdy element zawiera:
    - `id`: indeks opisu stanowiska w batchu,
    - `tags`: listę tagów ograniczoną do `ALLOWED_TAGS`.
    """
    return {
        "name": "job_tags_batch",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string", "enum": ALLOWED_TAGS},
                            },
                        },
                        "required": ["id", "tags"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["items"],
            "additionalProperties": False,
        },
    }


def _render_prompt(path: Path, **variables: str) -> str:
    """Ładuje szablon promptu z Markdown i podstawia zmienne.

    Używany jest `string.Template`, więc w plikach promptów stosujemy składnię
    placeholderów `$name` (np. `$jobs_text`).
    """
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    template = Template(path.read_text(encoding="utf-8"))
    return template.substitute(**variables)


def _developer_prompt() -> str:
    """Buduje treść promptu deweloperskiego z opisami tagów."""
    tags_desc = "\n".join(f"- {tag}: {desc}" for tag, desc in TAG_DESCRIPTIONS.items())
    return _render_prompt(TAG_JOBS_DEVELOPER_PROMPT_PATH, tags_descriptions=tags_desc)


def _user_prompt(jobs_text: str) -> str:
    """Buduje treść promptu użytkownika zawierającego listę stanowisk do klasyfikacji."""
    return _render_prompt(TAG_JOBS_USER_PROMPT_PATH, jobs_text=jobs_text)


def _chat_completion_with_retry(client: OpenAI, *, model: str, messages: list[dict], schema: dict):
    """Wysyła zapytanie do modelu z prostym mechanizmem retry i backoff.

    Przy błędzie wywołanie jest ponawiane do `MAX_RETRIES` razy. Gdy wszystkie
    próby zawiodą, funkcja przekazuje wyjątek dalej.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(
                model=model,
                temperature=0,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": schema},
            )
        except Exception:
            if attempt == MAX_RETRIES:
                raise
            time.sleep(0.7 * attempt)


def _clean_tags(tags: list[str]) -> list[str]:
    """Czyści listę tagów: usuwa duplikaty i odrzuca wartości spoza dozwolonej listy."""
    seen = set()
    out = []
    for tag in tags:
        if tag in ALLOWED_TAGS and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def _tag_jobs_batch(client: OpenAI, jobs: list[str], model: str) -> dict[int, list[str]]:
    """Taguje jedną partię opisów stanowisk pojedynczym wywołaniem LLM.

    Funkcja:
    - buduje numerowaną listę stanowisk,
    - wymusza odpowiedź w formacie JSON Schema,
    - parsuje i waliduje odpowiedź,
    - zwraca mapę `indeks_w_batchu -> tagi`.
    """
    if not jobs:
        return {}

    jobs_text = "\n".join(f"{i}. {job}" for i, job in enumerate(jobs))
    schema = _build_schema()
    messages = [
        {"role": "developer", "content": _developer_prompt()},
        {"role": "user", "content": _user_prompt(jobs_text)},
    ]

    completion = _chat_completion_with_retry(client, model=model, messages=messages, schema=schema)
    content = completion.choices[0].message.content or '{"items":[]}'
    data = json.loads(content)

    out: dict[int, list[str]] = {}
    for item in data.get("items", []):
        idx = item.get("id")
        if not isinstance(idx, int) or idx < 0 or idx >= len(jobs):
            continue
        out[idx] = _clean_tags(item.get("tags", []))
    return out


def tag_jobs(rows: list[dict], model: str, batch_size: int = DEFAULT_BATCH_SIZE) -> dict[int, list[str]]:
    """Taguje stanowiska dla wszystkich rekordów, optymalizując liczbę zapytań.

    Działanie:
    - normalizuje i deduplikuje identyczne opisy `job`,
    - wysyła unikalne opisy partiami (`batch_size`) do `_tag_jobs_batch`,
    - mapuje wynik z powrotem na indeksy oryginalnych rekordów.
    Zwraca mapę `indeks_rekordu -> lista_tagów`.
    """
    if not rows:
        return {}

    client = _get_openrouter_client()
    jobs_to_row_ids: dict[str, list[int]] = defaultdict(list)

    for row_idx, row in enumerate(rows):
        job = " ".join((row.get("job") or "").split())
        jobs_to_row_ids[job].append(row_idx)

    unique_jobs = list(jobs_to_row_ids.keys())
    result: dict[int, list[str]] = {}

    for offset in range(0, len(unique_jobs), batch_size):
        batch_jobs = unique_jobs[offset : offset + batch_size]
        batch_tags = _tag_jobs_batch(client, batch_jobs, model)
        for local_idx, job in enumerate(batch_jobs):
            tags = batch_tags.get(local_idx, [])
            for row_idx in jobs_to_row_ids[job]:
                result[row_idx] = tags

    return result


def build_answer(rows: list[dict], tags_map: dict[int, list[str]]) -> list[dict]:
    """Buduje finalną odpowiedź do API hubu na podstawie przefiltrowanych rekordów.

    Do wyniku trafiają tylko osoby z tagiem `transport`. Funkcja dba także o
    poprawne pole `born` (rok jako int) oraz o zgodny z zadaniem kształt obiektu.
    """
    answer = []
    for i, row in enumerate(rows):
        tags = tags_map.get(i, [])
        if "transport" not in tags:
            continue

        birth_year = row.get("born")
        if birth_year is None:
            birth_date = row.get("birthDate") or ""
            birth_year = int(str(birth_date).split("-", 1)[0]) if birth_date else None

        if birth_year is None:
            continue

        answer.append(
            {
                "name": row.get("name", ""),
                "surname": row.get("surname", ""),
                "gender": row.get("gender", ""),
                "born": int(birth_year),
                "city": row.get("city") or row.get("birthPlace") or "",
                "tags": tags,
            }
        )
    return answer


def send_answer(answer: list[dict], api_key: str, verify_url: str, task: str = "people") -> dict:
    """Wysyła gotową odpowiedź do endpointu weryfikacyjnego i zwraca JSON odpowiedzi."""
    payload = {"apikey": api_key, "task": task, "answer": answer}
    resp = requests.post(verify_url, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()
