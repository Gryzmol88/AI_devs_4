from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "categorize"
BASE_DIR = Path(__file__).resolve().parent
SEASON2_DIR = BASE_DIR.parent
PROJECT_ROOT = SEASON2_DIR.parent
DEFAULT_MODEL = "anthropic/claude-sonnet-4.6"
DEFAULT_BASE_PROMPT = (
    "Return one token: DNG or NEU. Reactor parts/components are always NEU. "
    "L:{label}; ID:{id}; DESC:{description}"
)
ITEM_LABELS = [chr(code) for code in range(ord("A"), ord("J") + 1)]


class VerifyAnswer(BaseModel):
    """Represents the `answer` object sent to the categorize verification endpoint."""

    prompt: str = Field(..., description="Prompt evaluated by hub for one item.")


class VerifyPayload(BaseModel):
    """Represents one POST payload for task `categorize` sent to `/verify`."""

    apikey: str
    task: str
    answer: VerifyAnswer


class ApiTraceEntry(BaseModel):
    """Stores one API exchange record used for terminal and JSONL tracing."""

    ts: str
    attempt: int | None = None
    step: str
    method: str
    url: str
    request_body: Any | None = None
    status_code: int | None = None
    response_body: Any | None = None
    error: str | None = None


@dataclass
class Item:
    """Single item row loaded from source CSV and normalized for prompting."""

    item_id: str
    description: str
    raw: dict[str, str]


@dataclass
class AppConfig:
    """Holds runtime configuration and credentials for the categorize automation flow."""

    api_key: str
    csv_url: str
    verify_url: str
    task_name: str
    openrouter_api_key: str
    openrouter_base_url: str
    prompt_engineer_model: str
    max_attempts: int
    request_timeout: int
    enable_reset: bool
    output_dir: Path
    reset_url: str | None
    max_prompt_tokens: int


def _load_env() -> None:
    """Loads environment variables from root and `Season2/.env` files."""

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(SEASON2_DIR / ".env")
    load_dotenv()


def _bool_env(name: str, default: bool) -> bool:
    """Parses boolean-like env variables with a safe default fallback."""

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _build_config() -> AppConfig:
    """Builds validated runtime configuration from environment variables."""

    _load_env()
    api_key = os.getenv("HUB_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Brak HUB_API_KEY/API_KEY w .env.")

    csv_url = (
        os.getenv("CATEGORIZE_CSV_URL", "").strip()
        or os.getenv("ITEMS_CSV_URL", "").strip()
    )
    if not csv_url:
        csv_url = f"https://hub.ag3nts.org/data/{api_key}/categorize.csv"

    output_dir = BASE_DIR / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        api_key=api_key,
        csv_url=csv_url,
        verify_url=os.getenv("VERIFY_URL", VERIFY_URL).strip(),
        task_name=os.getenv("CATEGORIZE_TASK_NAME", TASK_NAME).strip() or TASK_NAME,
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip(),
        prompt_engineer_model=os.getenv("PROMPT_ENGINEER_MODEL", DEFAULT_MODEL).strip(),
        max_attempts=int(os.getenv("MAX_PROMPT_ATTEMPTS", "12")),
        request_timeout=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        enable_reset=_bool_env("ENABLE_CATEGORIZE_RESET", True),
        output_dir=output_dir,
        reset_url=os.getenv("CATEGORIZE_RESET_URL", "").strip() or None,
        max_prompt_tokens=int(os.getenv("MAX_PROMPT_TOKENS", "100")),
    )


def _now() -> str:
    """Returns local timestamp used for logs and trace entries."""

    return datetime.now().isoformat(timespec="seconds")


def _write_json(path: Path, payload: Any) -> None:
    """Writes structured JSON payload to disk with UTF-8 formatting."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _append_jsonl(path: Path, payload: Any) -> None:
    """Appends one JSON object line into a JSONL file for incremental traces."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _find_flag(payload: Any) -> str | None:
    """Extracts first `{FLG:...}` token from any JSON-serializable response payload."""

    blob = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"\{FLG:[^}]+\}", blob)
    return match.group(0) if match else None


def _pick(row: dict[str, str], candidates: list[str]) -> str:
    """Returns first non-empty value from row by normalized candidate column names."""

    lowered = {str(k).strip().lower(): str(v).strip() for k, v in row.items()}
    for key in candidates:
        if key in lowered and lowered[key]:
            return lowered[key]
    return ""


def _print_attempt_header(attempt: int, max_attempts: int, prompt_template: str) -> None:
    """Prints clear separator for a new prompt iteration with current template summary."""

    print("\n" + "=" * 88)
    print(f"ITERATION {attempt}/{max_attempts}")
    print("=" * 88)
    print(f"TEMPLATE: {prompt_template}")


def _log_api_exchange(cfg: AppConfig, entry: ApiTraceEntry) -> None:
    """Prints and persists every outbound API request with matching response/error details."""

    print("\n" + "-" * 88)
    attempt_label = f"ATTEMPT {entry.attempt}" if entry.attempt is not None else "ATTEMPT N/A"
    print(f"API EXCHANGE [{attempt_label}] [{entry.step}]")
    print("-" * 88)
    print(f"REQUEST: {entry.method} {entry.url}")
    if entry.request_body is not None:
        print("REQUEST BODY:")
        print(json.dumps(entry.request_body, ensure_ascii=False, indent=2))

    if entry.error:
        print(f"ERROR: {entry.error}")
    else:
        print(f"STATUS: {entry.status_code}")
        print("RESPONSE BODY:")
        print(json.dumps(entry.response_body, ensure_ascii=False, indent=2))

    _append_jsonl(cfg.output_dir / "api_trace.jsonl", entry.model_dump())


def fetch_items(cfg: AppConfig, attempt: int) -> list[Item]:
    """Downloads fresh CSV from hub, saves snapshot and returns normalized list of items."""

    trace = ApiTraceEntry(
        ts=_now(),
        attempt=attempt,
        step="FETCH_CSV",
        method="GET",
        url=cfg.csv_url,
    )
    try:
        response = requests.get(cfg.csv_url, timeout=cfg.request_timeout)
        response.raise_for_status()
        trace.status_code = response.status_code
        trace.response_body = {
            "headers": dict(response.headers),
            "csv_preview": response.text[:500],
            "csv_length": len(response.text),
        }
        _log_api_exchange(cfg, trace)
    except Exception as error:  # noqa: BLE001
        trace.error = str(error)
        _log_api_exchange(cfg, trace)
        raise

    csv_text = response.text
    (cfg.output_dir / "items_latest.csv").write_text(csv_text, encoding="utf-8")

    reader = csv.DictReader(csv_text.splitlines())
    items: list[Item] = []
    for row in reader:
        item_id = _pick(row, ["id", "item_id", "itemid", "uid", "code", "symbol"])
        description = _pick(row, ["description", "desc", "opis", "details", "item_description"])
        if not item_id:
            item_id = str(len(items) + 1)
        if not description:
            joined = " | ".join(f"{k}:{v}" for k, v in row.items() if str(v).strip())
            description = joined or "(empty)"
        items.append(Item(item_id=item_id, description=description, raw=dict(row)))

    if len(items) < 10:
        raise RuntimeError(f"CSV zawiera mniej niz 10 rekordow: {len(items)}")
    if len(items) > 10:
        print(f"[warn] CSV zawiera {len(items)} rekordow. Uzywam pierwszych 10 zgodnie z zadaniem.")
    return items[:10]


def estimate_tokens(text: str) -> int:
    """Estimates token count using tiktoken when available, with fallback approximation."""

    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return int(len(text) / 4) + 1


def build_prompt(prompt_template: str, item: Item, label: str) -> str:
    """Builds concrete classify prompt for one item from the active template."""

    return prompt_template.format(id=item.item_id, description=item.description, label=label)


def build_prompt_under_budget(
    prompt_template: str,
    item: Item,
    label: str,
    max_tokens: int,
) -> tuple[str, int, bool]:
    """Builds prompt that fits max token budget by truncating description when needed."""

    full_prompt = build_prompt(prompt_template, item, label)
    full_tokens = estimate_tokens(full_prompt)
    if full_tokens <= max_tokens:
        return full_prompt, full_tokens, False

    # Binary search finds the longest description prefix that still fits the budget.
    original_desc = item.description
    low = 0
    high = len(original_desc)
    best_prompt = ""
    best_tokens = -1
    best_desc = ""

    while low <= high:
        mid = (low + high) // 2
        desc_candidate = original_desc[:mid]
        prompt_candidate = prompt_template.format(
            id=item.item_id,
            description=desc_candidate,
            label=label,
        )
        token_candidate = estimate_tokens(prompt_candidate)

        if token_candidate <= max_tokens:
            best_prompt = prompt_candidate
            best_tokens = token_candidate
            best_desc = desc_candidate
            low = mid + 1
        else:
            high = mid - 1

    if not best_prompt:
        raise RuntimeError(
            f"Nie da sie zmiescic promptu w limicie {max_tokens} tokenow "
            f"(nawet z pustym opisem) dla ID={item.item_id}."
        )

    return best_prompt, best_tokens, best_desc != original_desc


def verify_prompt_for_item(cfg: AppConfig, prompt: str, attempt: int, index: int, item_id: str) -> dict[str, Any]:
    """Sends one categorize verify request and returns parsed JSON response payload."""

    payload = VerifyPayload(apikey=cfg.api_key, task=cfg.task_name, answer=VerifyAnswer(prompt=prompt))
    trace = ApiTraceEntry(
        ts=_now(),
        attempt=attempt,
        step=f"VERIFY_ITEM_{index}_ID_{item_id}",
        method="POST",
        url=cfg.verify_url,
        request_body=payload.model_dump(),
    )

    try:
        response = requests.post(
            cfg.verify_url,
            json=payload.model_dump(),
            timeout=cfg.request_timeout,
        )
        response.raise_for_status()
        body = response.json()
        trace.status_code = response.status_code
        trace.response_body = body
        _log_api_exchange(cfg, trace)
        return body
    except Exception as error:  # noqa: BLE001
        trace.error = str(error)
        _log_api_exchange(cfg, trace)
        raise


def try_reset(cfg: AppConfig, attempt: int) -> None:
    """Attempts hub reset between iterations using configured and fallback payload variants."""

    if not cfg.enable_reset or attempt == 1:
        return

    variants: list[tuple[str, dict[str, Any]]] = []
    if cfg.reset_url:
        variants.append((cfg.reset_url, {"apikey": cfg.api_key}))

    variants.extend(
        [
            (
                cfg.verify_url,
                VerifyPayload(
                    apikey=cfg.api_key,
                    task=cfg.task_name,
                    answer=VerifyAnswer(prompt="reset"),
                ).model_dump(),
            ),
        ]
    )

    for pos, (url, payload) in enumerate(variants, start=1):
        trace = ApiTraceEntry(
            ts=_now(),
            attempt=attempt,
            step=f"RESET_VARIANT_{pos}",
            method="POST",
            url=url,
            request_body=payload,
        )
        try:
            resp = requests.post(url, json=payload, timeout=cfg.request_timeout)
            body: Any
            try:
                body = resp.json()
            except Exception:
                body = {"text": resp.text[:1000]}
            trace.status_code = resp.status_code
            trace.response_body = body
            _log_api_exchange(cfg, trace)
            if resp.status_code < 400:
                break
        except Exception as error:  # noqa: BLE001
            trace.error = str(error)
            _log_api_exchange(cfg, trace)


def run_cycle(
    cfg: AppConfig,
    prompt_template: str,
    attempt: int,
) -> tuple[bool, str | None, list[dict[str, Any]], list[Item]]:
    """Runs one full iteration: optional reset, CSV fetch, 10 classify calls, and flag detection."""

    try_reset(cfg, attempt)
    items = fetch_items(cfg, attempt)
    cycle_log: list[dict[str, Any]] = []

    for index, item in enumerate(items, start=1):
        print("\n" + "~" * 88)
        print(f"ITEM {index}/{len(items)} | ID={item.item_id}")
        print("~" * 88)
        label = ITEM_LABELS[index - 1]

        prompt, token_est, was_truncated = build_prompt_under_budget(
            prompt_template=prompt_template,
            item=item,
            label=label,
            max_tokens=cfg.max_prompt_tokens,
        )
        record: dict[str, Any] = {
            "ts": _now(),
            "attempt": attempt,
            "index": index,
            "label": label,
            "id": item.item_id,
            "description": item.description,
            "token_estimate": token_est,
            "prompt": prompt,
            "description_truncated": was_truncated,
        }

        try:
            response = verify_prompt_for_item(
                cfg=cfg,
                prompt=prompt,
                attempt=attempt,
                index=index,
                item_id=item.item_id,
            )
            record["response"] = response
            flag = _find_flag(response)
            if flag:
                cycle_log.append(record)
                _append_jsonl(cfg.output_dir / "cycle_log.jsonl", record)
                return True, flag, cycle_log, items
        except Exception as error:  # noqa: BLE001
            record["error"] = str(error)
            cycle_log.append(record)
            _append_jsonl(cfg.output_dir / "cycle_log.jsonl", record)
            return False, None, cycle_log, items

        cycle_log.append(record)
        _append_jsonl(cfg.output_dir / "cycle_log.jsonl", record)

    return False, None, cycle_log, items


def build_feedback(cycle_log: list[dict[str, Any]]) -> str:
    """Builds compact feedback digest from last iteration responses for prompt refinement."""

    compact: list[str] = []
    for row in cycle_log:
        if "error" in row:
            compact.append(f"ID={row.get('id')} ERROR={row['error']}")
            continue
        response = row.get("response", {})
        response_blob = json.dumps(response, ensure_ascii=False)[:500]
        compact.append(f"ID={row.get('id')} RESP={response_blob}")
    return "\n".join(compact[-10:])


def improve_prompt_with_llm(
    cfg: AppConfig,
    current_template: str,
    feedback: str,
    sample_items: list[Item],
    attempt: int,
) -> str:
    """Uses OpenRouter LLM as prompt-engineer to produce next improved prompt template."""

    if not cfg.openrouter_api_key:
        return current_template

    samples = "\n".join(
        f"- id={item.item_id}, description={item.description}" for item in sample_items[:3]
    )
    system = (
        "You are a prompt engineer. Produce a compact prompt template for binary classification.\n"
        "Requirements:\n"
        "1) Total prompt (template + item data) must fit <=100 tokens.\n"
        "2) Output must force single-token answer DNG or NEU.\n"
        "3) Reactor parts/components must always be NEU.\n"
        "4) Include label marker placeholder exactly as L:{label}.\n"
        "5) Keep static prefix stable for caching.\n"
        "Return JSON only: {\"template\":\"...\"} with placeholders {label}, {id}, and {description}."
    )
    user = (
        f"Current template:\n{current_template}\n\n"
        f"Hub feedback:\n{feedback}\n\n"
        f"Sample items:\n{samples}\n\n"
        "Generate improved template."
    )

    trace = ApiTraceEntry(
        ts=_now(),
        attempt=attempt,
        step="PROMPT_ENGINEER",
        method="POST",
        url=f"{cfg.openrouter_base_url}/chat/completions",
        request_body={
            "model": cfg.prompt_engineer_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        },
    )

    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)
    try:
        response = client.chat.completions.create(
            model=cfg.prompt_engineer_model,
            temperature=0.2,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        content = response.choices[0].message.content or ""
        trace.status_code = 200
        trace.response_body = {"content": content}
        _log_api_exchange(cfg, trace)
        _append_jsonl(
            cfg.output_dir / "model_responses.jsonl",
            {
                "ts": _now(),
                "attempt": attempt,
                "step": "PROMPT_ENGINEER",
                "model": cfg.prompt_engineer_model,
                "response_content": content,
            },
        )
    except Exception as error:  # noqa: BLE001
        trace.error = str(error)
        _log_api_exchange(cfg, trace)
        return current_template

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            return current_template
        data = json.loads(match.group(0))
    template = str(data.get("template", "")).strip()
    if "{id}" in template and "{description}" in template and "{label}" in template:
        return template
    return current_template


def main() -> None:
    """Executes iterative categorize workflow until flag is found or attempts are exhausted."""

    cfg = _build_config()
    prompt_template = os.getenv("CATEGORIZE_PROMPT_TEMPLATE", DEFAULT_BASE_PROMPT)

    run_meta = {
        "started_at": _now(),
        "model": cfg.prompt_engineer_model,
        "verify_url": cfg.verify_url,
        "task": cfg.task_name,
        "csv_url": cfg.csv_url,
    }
    _write_json(cfg.output_dir / "run_meta.json", run_meta)

    for attempt in range(1, cfg.max_attempts + 1):
        _print_attempt_header(attempt, cfg.max_attempts, prompt_template)
        _write_json(cfg.output_dir / "current_prompt.json", {"attempt": attempt, "template": prompt_template})

        success, flag, cycle_log, items_for_context = run_cycle(cfg, prompt_template, attempt)
        if success and flag:
            print(f"\nFLAG FOUND: {flag}")
            _write_json(
                cfg.output_dir / "result.json",
                {"ok": True, "flag": flag, "attempt": attempt, "template": prompt_template},
            )
            return

        feedback = build_feedback(cycle_log)
        _write_json(cfg.output_dir / f"attempt_{attempt:02d}_feedback.json", {"feedback": feedback})
        prompt_template = improve_prompt_with_llm(
            cfg=cfg,
            current_template=prompt_template,
            feedback=feedback,
            sample_items=items_for_context,
            attempt=attempt,
        )

    print("\nNo flag found within max attempts.")
    _write_json(cfg.output_dir / "result.json", {"ok": False, "message": "No flag found"})


if __name__ == "__main__":
    main()
