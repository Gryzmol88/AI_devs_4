from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

ZMAIL_URL = "https://hub.ag3nts.org/api/zmail"
VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "mailbox"

FLAG_PATTERN = re.compile(r"\{FLG:[^}]+\}")
SEC_CODE_PATTERN = re.compile(r"SEC-[A-Za-z0-9]{28,40}")
DATE_PATTERN = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
SIDE_HINT = "Mam wiadomość! No nareszcie!"
RATE_LIMIT_MARKERS = ("HTTP 429", "Za często wykonujesz zapytania", "rate limit")


class AppConfig(BaseModel):
    """Stores runtime configuration for the mailbox solver.

    The model is intentionally strict because the mission loop should fail fast
    when required values are missing or malformed. The fields are grouped into
    four concerns:

    1. API access (`hub_api_key`, endpoint URLs).
    2. Search and polling behavior (`max_rounds`, `poll_seconds`).
    3. Pagination control (`search_pages`, `inbox_pages`, `per_page`).
    4. Filesystem output strategy (`output_dir`).

    By keeping this in a Pydantic model we get consistent validation and a
    single source of truth that can be dumped to JSON for reproducibility.
    """

    hub_api_key: str
    openrouter_api_key: str
    zmail_url: str = ZMAIL_URL
    verify_url: str = VERIFY_URL
    task_name: str = TASK_NAME
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "openai/gpt-4.1-mini"
    max_agent_steps: int = Field(default=24, ge=4, le=200)

    max_rounds: int = Field(default=8, ge=1, le=80)
    poll_seconds: float = Field(default=2.0, ge=0.0, le=120.0)
    api_delay_seconds: float = Field(default=0.2, ge=0.0, le=5.0)

    search_pages: int = Field(default=1, ge=1, le=50)
    inbox_pages: int = Field(default=1, ge=1, le=50)
    use_inbox: bool = True
    per_page: int = Field(default=20, ge=5, le=20)
    max_messages_per_round: int = Field(default=10, ge=1, le=200)
    max_threads_per_round: int = Field(default=2, ge=0, le=50)

    request_timeout_seconds: int = Field(default=45, ge=5, le=240)
    output_dir: Path

    @field_validator("hub_api_key")
    @classmethod
    def _validate_api_key(cls, value: str) -> str:
        """Ensures API key is present and not blank after trimming whitespace."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("HUB_API_KEY cannot be empty.")
        return cleaned

    @field_validator("openrouter_api_key")
    @classmethod
    def _validate_openrouter_key(cls, value: str) -> str:
        """Ensures OpenRouter API key for agentic function-calling is present."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("OPENROUTER_API_KEY cannot be empty.")
        return cleaned


class MailHeader(BaseModel):
    """Represents one mail metadata record returned by `search` or `getInbox`.

    API returns lightweight items in listing endpoints. This model captures keys
    needed for follow-up calls (`rowID`/`messageID`) and for ranking relevance.
    """

    rowID: int | None = None
    messageID: str | None = None
    threadID: int | None = None
    subject: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""
    snippet: str = ""

    def stable_id(self) -> str:
        """Returns canonical identifier used for deduplication and file naming.

        Preference order:
        - `messageID` when present (stable hash-like id),
        - `rowID` fallback,
        - synthetic marker when API gives incomplete data.
        """

        if self.messageID:
            return self.messageID
        if self.rowID is not None:
            return f"row-{self.rowID}"
        return "unknown-id"


class MailBody(BaseModel):
    """Represents one full message returned by `getMessages`.

    The API returns `items` where each item includes message text. We normalize
    fields with defaults so downstream extraction can work without many checks.
    """

    rowID: int | None = None
    messageID: str | None = None
    threadID: int | None = None
    subject: str = ""
    message: str = ""
    from_: str = Field(default="", alias="from")
    to: str = ""
    date: str = ""

    def stable_id(self) -> str:
        """Returns canonical id for this message for deduplication and outputs."""

        if self.messageID:
            return self.messageID
        if self.rowID is not None:
            return f"row-{self.rowID}"
        return "unknown-id"


class MissionAnswer(BaseModel):
    """Keeps currently known values for the primary mission answer.

    Partial answers are expected during exploration. We keep nullable fields so
    the solver can iteratively improve values after `/verify` feedback.
    """

    password: str | None = None
    date: str | None = None
    confirmation_code: str | None = None

    def as_payload(self) -> dict[str, Any]:
        """Builds payload object exactly in schema expected by `/verify`."""

        return {
            "password": self.password,
            "date": self.date,
            "confirmation_code": self.confirmation_code,
        }


class CandidateEvidence(BaseModel):
    """Stores one extracted candidate with source metadata.

    This structure is useful for auditability: we keep where value came from,
    why it was selected, and which mail id supported the extraction.
    """

    field_name: str
    value: str
    reason: str
    message_id: str
    subject: str
    sender: str
    date: str


class RuntimeSnapshot(BaseModel):
    """Captures full run state for debugging and reproducibility.

    The snapshot is written to output so each run can be replayed or reviewed
    without repeating network calls. It includes current answer, evidences,
    feedback history, and optional flags.
    """

    round_no: int
    answer: MissionAnswer
    evidences: list[CandidateEvidence] = Field(default_factory=list)
    verify_feedbacks: list[dict[str, Any]] = Field(default_factory=list)
    found_flag_main: str | None = None
    found_flag_side: str | None = None


@dataclass
class RunPaths:
    """Aggregates all output paths created for a single run timestamp.

    This dataclass is non-validated on purpose because paths are deterministic
    and derived from filesystem operations. It keeps code readable by avoiding
    repeated path composition scattered across the script.
    """

    run_dir: Path
    all_messages_dir: Path
    selected_messages_dir: Path
    logs_jsonl: Path
    result_json: Path
    llm_trace_jsonl: Path


@dataclass
class AgentRuntime:
    """Mutable runtime caches used by tool handlers in function-calling loop."""

    headers: dict[str, MailHeader]
    messages: dict[str, MailBody]
    verify_feedbacks: list[dict[str, Any]]
    found_flag_main: str | None
    found_flag_side: str | None
    expanded_threads: set[int]


def now_iso() -> str:
    """Returns current timestamp in ISO format used in logs and artifacts."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Prints human-readable runtime logs to the console."""

    print(f"[{now_iso()}] {message}")


def setup_environment(project_root: Path, season2_dir: Path) -> None:
    """Loads environment variables from project-level and Season2-level `.env`.

    Loading order is intentional:
    1. project root `.env` (shared defaults),
    2. `Season2/.env` (season-specific overrides),
    3. current process environment (already present, highest priority).

    We do not override existing process values to preserve explicit runtime
    injections from CI or terminal invocation.
    """

    load_env_file(project_root / ".env")
    load_env_file(season2_dir / ".env")


def load_env_file(path: Path) -> None:
    """Loads simple KEY=VALUE pairs from `.env` file into process env.

    The parser intentionally supports only common cases and ignores comments,
    blank lines, and malformed rows. Existing environment variables are not
    overridden to preserve explicit runtime values.
    """

    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_config(base_dir: Path) -> AppConfig:
    """Creates validated runtime configuration from environment and defaults.

    The function centralizes translation from plain env vars into typed values.
    It also creates base output directory path under `Season2/mailbox/output`.
    """

    hub_api_key = os.getenv("HUB_API_KEY", "")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "")
    output_dir = base_dir / "output"

    cfg = AppConfig(
        hub_api_key=hub_api_key,
        openrouter_api_key=openrouter_api_key,
        zmail_url=os.getenv("ZMAIL_URL", ZMAIL_URL),
        verify_url=os.getenv("VERIFY_URL", VERIFY_URL),
        task_name=os.getenv("MAILBOX_TASK_NAME", TASK_NAME),
        openrouter_base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        llm_model=os.getenv("MAILBOX_MODEL", "openai/gpt-4.1-mini"),
        max_agent_steps=int(os.getenv("MAILBOX_MAX_AGENT_STEPS", "24")),
        max_rounds=int(os.getenv("MAILBOX_MAX_ROUNDS", "8")),
        poll_seconds=float(os.getenv("MAILBOX_POLL_SECONDS", "2.0")),
        api_delay_seconds=float(os.getenv("MAILBOX_API_DELAY_SECONDS", "0.2")),
        search_pages=int(os.getenv("MAILBOX_SEARCH_PAGES", "1")),
        inbox_pages=int(os.getenv("MAILBOX_INBOX_PAGES", "1")),
        use_inbox=os.getenv("MAILBOX_USE_INBOX", "1").lower() in {"1", "true", "yes"},
        per_page=int(os.getenv("MAILBOX_PER_PAGE", "20")),
        max_messages_per_round=int(os.getenv("MAILBOX_MAX_MESSAGES_PER_ROUND", "10")),
        max_threads_per_round=int(os.getenv("MAILBOX_MAX_THREADS_PER_ROUND", "2")),
        request_timeout_seconds=int(os.getenv("MAILBOX_TIMEOUT", "45")),
        output_dir=output_dir,
    )
    return cfg


def init_run_paths(output_dir: Path) -> RunPaths:
    """Creates timestamped run directories and returns strongly-typed paths.

    Folder layout:
    - `output/<ts>/all_messages`: every fetched full message,
    - `output/<ts>/selected_messages`: only mission-relevant messages,
    - `output/<ts>/run_trace.jsonl`: step-by-step structured log,
    - `output/<ts>/result.json`: final summary and extracted values.
    """

    run_dir = output_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    all_messages_dir = run_dir / "all_messages"
    selected_messages_dir = run_dir / "selected_messages"
    all_messages_dir.mkdir(parents=True, exist_ok=True)
    selected_messages_dir.mkdir(parents=True, exist_ok=True)

    return RunPaths(
        run_dir=run_dir,
        all_messages_dir=all_messages_dir,
        selected_messages_dir=selected_messages_dir,
        logs_jsonl=run_dir / "run_trace.jsonl",
        result_json=run_dir / "result.json",
        llm_trace_jsonl=run_dir / "llm_trace.jsonl",
    )


def clear_output_root(output_dir: Path) -> None:
    """Deletes all previous run artifacts from output root directory.

    Called at agent startup so each run starts with a clean `output` folder,
    as requested by the workflow.
    """

    if not output_dir.exists():
        return
    for child in output_dir.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            try:
                child.unlink()
            except FileNotFoundError:
                pass


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Appends one JSON record per line to support easy timeline inspection."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_json(path: Path, payload: Any) -> None:
    """Writes pretty-formatted UTF-8 JSON artifact to disk."""

    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    """Executes JSON POST request with stdlib urllib and returns decoded JSON.

    We use stdlib here to avoid external dependency on `requests` in training
    environments where only base Python packages are available.
    """

    body = json.dumps(payload).encode("utf-8")
    req = urlrequest.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8", errors="replace")
        return json.loads(raw)
    except urlerror.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
    except urlerror.URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def safe_filename(value: str) -> str:
    """Converts arbitrary text to filesystem-safe ASCII-ish filename fragment."""

    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", value)
    cleaned = cleaned.strip("_")
    return cleaned[:120] if cleaned else "message"


def zmail_call(cfg: AppConfig, action: str, **kwargs: Any) -> dict[str, Any]:
    """Executes one POST call to `zmail` endpoint and returns parsed JSON.

    The function is generic on purpose so higher-level methods can focus on
    mission logic, not transport details. It injects `apikey` and `action` for
    every request, validates HTTP status, and raises explicit runtime errors.
    """

    payload: dict[str, Any] = {"apikey": cfg.hub_api_key, "action": action}
    payload.update(kwargs)
    log(f"zmail action={action} kwargs={kwargs}")

    for attempt in range(1, 5):
        try:
            result = post_json(cfg.zmail_url, payload, cfg.request_timeout_seconds)
            if cfg.api_delay_seconds > 0:
                time.sleep(cfg.api_delay_seconds)
            return result
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            is_rate_limited = any(marker in text for marker in RATE_LIMIT_MARKERS)
            if not is_rate_limited or attempt == 4:
                raise
            log(f"zmail rate-limited on action={action}, retry={attempt}/4")

            # Best-effort reset endpoint from zmail help; ignore reset errors.
            try:
                post_json(
                    cfg.zmail_url,
                    {"apikey": cfg.hub_api_key, "action": "reset"},
                    cfg.request_timeout_seconds,
                )
            except Exception:
                pass
            time.sleep(min(8.0, 1.5 * attempt))

    raise RuntimeError("Unexpected zmail retry loop exit.")


def verify_call(cfg: AppConfig, answer: MissionAnswer) -> dict[str, Any]:
    """Sends current mission answer to central `/verify` endpoint.

    The endpoint accepts partial or complete answer object. We always keep the
    same schema and let server feedback drive the next discovery iteration.
    """

    payload = {
        "apikey": cfg.hub_api_key,
        "task": cfg.task_name,
        "answer": answer.as_payload(),
    }
    log(f"verify task={cfg.task_name} answer={answer.model_dump()}")
    for attempt in range(1, 4):
        try:
            return post_json(cfg.verify_url, payload, cfg.request_timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            text = str(exc)
            is_rate_limited = any(marker in text for marker in RATE_LIMIT_MARKERS)
            if not is_rate_limited or attempt == 3:
                raise
            log(f"verify rate-limited, retry={attempt}/3")
            time.sleep(min(8.0, 2.0 * attempt))
    raise RuntimeError("Unexpected verify retry loop exit.")


def parse_headers(items: list[dict[str, Any]]) -> list[MailHeader]:
    """Converts raw API list results into validated `MailHeader` objects.

    Invalid records are skipped deliberately because one malformed item should
    not crash the whole search loop.
    """

    parsed: list[MailHeader] = []
    for item in items:
        try:
            parsed.append(MailHeader.model_validate(item))
        except Exception:
            continue
    return parsed


def parse_bodies(items: list[dict[str, Any]]) -> list[MailBody]:
    """Converts raw `getMessages.items` into validated `MailBody` objects."""

    parsed: list[MailBody] = []
    for item in items:
        try:
            parsed.append(MailBody.model_validate(item))
        except Exception:
            continue
    return parsed


def score_header_relevance(header: MailHeader) -> int:
    """Scores header-level relevance before full body fetch.

    We prioritize fetch budget for likely useful emails by looking at sender,
    subject and snippet only (cheap metadata available from search/listing).
    """

    haystack = "\n".join([header.subject, header.snippet, header.from_, header.to]).lower()
    score = 0
    if "proton.me" in haystack:
        score += 3
    if "security" in haystack:
        score += 4
    if "sec-" in haystack or "ticket" in haystack:
        score += 5
    if "atak" in haystack or "bomb" in haystack or "elektrow" in haystack:
        score += 6
    if "has" in haystack or "password" in haystack or "pracownicz" in haystack:
        score += 4
    return score


def find_flags(text: str) -> list[str]:
    """Extracts all main mission flag tokens of shape `{FLG:...}` from text."""

    return FLAG_PATTERN.findall(text or "")


def contains_side_hint(text: str) -> bool:
    """Checks whether text contains side-quest hint phrase (case-insensitive)."""

    return SIDE_HINT.lower() in (text or "").lower()


def extract_confirmation_codes(text: str) -> list[str]:
    """Extracts valid security confirmation codes from free-form message text."""

    raw_codes = SEC_CODE_PATTERN.findall(text or "")
    codes: list[str] = []
    for raw_code in raw_codes:
        normalized = normalize_confirmation_code(raw_code)
        if normalized:
            codes.append(normalized)
    unique_codes = sorted(set(codes), key=len, reverse=True)
    return unique_codes


def normalize_confirmation_code(value: str) -> str | None:
    """Normalizes confirmation code to `SEC-` + alnum suffix (28..40 chars).

    Some messages contain slightly different code lengths. We keep the full
    normalized suffix (not a truncated one), because payload validation in the
    target API can accept longer variants.
    """

    if not value or not value.startswith("SEC-"):
        return None
    suffix = re.sub(r"[^A-Za-z0-9]", "", value[4:])
    if len(suffix) < 28:
        return None
    if len(suffix) > 40:
        suffix = suffix[:40]
    normalized = f"SEC-{suffix}"
    if len(normalized) < 32:
        return None
    return normalized


def extract_dates(text: str) -> list[str]:
    """Extracts `YYYY-MM-DD` dates from message text without semantic filtering."""

    return DATE_PATTERN.findall(text or "")


def best_confirmation_code_from_messages(messages: dict[str, MailBody]) -> str | None:
    """Finds best confirmation code with strong priority for correction mails.

    Preference order:
    1. messages containing 'poprawny' (explicit correction),
    2. longer code variant (often includes missing trailing character),
    3. newer message date.
    """

    ranked: list[tuple[int, str, str]] = []
    for msg in messages.values():
        text = "\n".join([msg.subject, msg.message, msg.from_, msg.to])
        text_lower = text.lower()
        correction_boost = 100 if "poprawny" in text_lower else 0
        for code in extract_confirmation_codes(text):
            ranked.append((correction_boost + len(code), code, msg.date))
    if not ranked:
        return None
    ranked.sort(key=lambda x: (x[0], x[2]), reverse=True)
    return ranked[0][1]


def score_message_relevance(message: MailBody) -> int:
    """Computes heuristic relevance score for selecting mission-important mails.

    Heuristics are intentionally simple and explainable. Points are awarded for
    known entities and indicators related to mission fields:
    - sender domain and security team,
    - keywords about attack plans,
    - password-related phrasing,
    - presence of `SEC-` confirmation code,
    - proton sender (Wiktor clue).
    """

    haystack = "\n".join(
        [message.subject, message.message, message.from_, message.to]
    ).lower()
    score = 0

    if "proton.me" in haystack:
        score += 3
    if "security" in haystack:
        score += 4
    if "atak" in haystack or "bomb" in haystack or "zbombard" in haystack:
        score += 6
    if "has" in haystack or "password" in haystack:
        score += 5
    if SEC_CODE_PATTERN.search(haystack):
        score += 7
    if DATE_PATTERN.search(haystack):
        score += 3
    return score


def save_message_json(base_dir: Path, message: MailBody, extra: dict[str, Any] | None = None) -> Path:
    """Writes one full message artifact as JSON and returns resulting path."""

    payload = message.model_dump(by_alias=True)
    if extra:
        payload["_extra"] = extra
    filename = f"{safe_filename(message.stable_id())}.json"
    path = base_dir / filename
    write_json(path, payload)
    return path


def save_message_markdown(base_dir: Path, message: MailBody, title_prefix: str = "") -> Path:
    """Writes one full message as readable Markdown for manual inspection.

    This export complements JSON logs and makes quick human review easier when
    comparing candidate evidences or searching side-mission hints.
    """

    filename = f"{safe_filename(message.stable_id())}.md"
    path = base_dir / filename
    header = f"{title_prefix} {message.subject}".strip()
    md = (
        f"# {header}\n\n"
        f"- id: `{message.stable_id()}`\n"
        f"- from: `{message.from_}`\n"
        f"- to: `{message.to}`\n"
        f"- date: `{message.date}`\n\n"
        "## Body\n\n"
        f"{message.message}\n"
    )
    path.write_text(md, encoding="utf-8")
    return path


def discover_mail_headers(cfg: AppConfig, trace_path: Path, queries: list[str]) -> dict[str, MailHeader]:
    """Collects candidate mail headers from inbox pages and targeted searches.

    The function merges results from multiple API calls into a deduplicated map
    indexed by stable message id. We intentionally combine broad and focused
    queries to avoid missing late-arriving emails in an active mailbox.
    """

    found: dict[str, MailHeader] = {}

    if cfg.use_inbox:
        for page in range(1, cfg.inbox_pages + 1):
            try:
                raw = zmail_call(cfg, "getInbox", page=page, perPage=cfg.per_page)
            except Exception as exc:  # noqa: BLE001
                append_jsonl(
                    trace_path,
                    {
                        "ts": now_iso(),
                        "step": "getInbox_error",
                        "page": page,
                        "error": str(exc),
                    },
                )
                if "outside the available range" in str(exc):
                    break
                raise
            append_jsonl(trace_path, {"ts": now_iso(), "step": "getInbox", "page": page, "raw": raw})
            headers = parse_headers(raw.get("items", []))
            log(f"getInbox page={page} hits={len(headers)}")
            for header in headers:
                found[header.stable_id()] = header
            total_pages = int(raw.get("pagination", {}).get("totalPages", page))
            if page >= total_pages:
                break

    for query in queries:
        for page in range(1, cfg.search_pages + 1):
            try:
                raw = zmail_call(cfg, "search", query=query, page=page, perPage=cfg.per_page)
            except Exception as exc:  # noqa: BLE001
                append_jsonl(
                    trace_path,
                    {
                        "ts": now_iso(),
                        "step": "search_error",
                        "query": query,
                        "page": page,
                        "error": str(exc),
                    },
                )
                if "outside the available range" in str(exc):
                    break
                raise
            append_jsonl(
                trace_path,
                {"ts": now_iso(), "step": "search", "query": query, "page": page, "raw": raw},
            )
            headers = parse_headers(raw.get("items", []))
            log(f"search query='{query}' page={page} hits={len(headers)}")
            for header in headers:
                found[header.stable_id()] = header
            total_pages = int(raw.get("pagination", {}).get("totalPages", page))
            if page >= total_pages:
                break

    log(f"discover_mail_headers total_deduped={len(found)}")
    return found


def fetch_full_messages(
    cfg: AppConfig,
    trace_path: Path,
    headers: dict[str, MailHeader],
    max_messages: int,
    max_threads: int,
) -> dict[str, MailBody]:
    """Fetches complete message bodies for each deduplicated header candidate.

    We use `getMessages(ids=...)` one-by-one for reliability and clearer logs.
    This is slower but easier to debug in a training context.
    """

    bodies: dict[str, MailBody] = {}
    ranked_headers = sorted(headers.values(), key=score_header_relevance, reverse=True)
    top_headers = ranked_headers[:max_messages]
    lookup_ids: list[str | int] = []
    for header in top_headers:
        lookup_id: str | int | None = header.messageID if header.messageID else header.rowID
        if lookup_id is not None:
            lookup_ids.append(lookup_id)

    if lookup_ids:
        raw = zmail_call(cfg, "getMessages", ids=lookup_ids)
        append_jsonl(
            trace_path,
            {
                "ts": now_iso(),
                "step": "getMessages_batch",
                "lookup_ids_count": len(lookup_ids),
                "lookup_ids": lookup_ids,
                "raw": raw,
            },
        )
        parsed = parse_bodies(raw.get("items", []))
        for message in parsed:
            bodies[message.stable_id()] = message

    # Expand critical threads to avoid missing follow-up corrections in replies.
    thread_candidates: list[int] = []
    for header in top_headers:
        if header.threadID is None:
            continue
        haystack = "\n".join([header.subject, header.snippet, header.from_]).lower()
        if "sec-" in haystack or "ticket" in haystack or "security" in haystack:
            thread_candidates.append(header.threadID)

    seen_threads: set[int] = set()
    for thread_id in thread_candidates:
        if thread_id in seen_threads:
            continue
        seen_threads.add(thread_id)
        if len(seen_threads) > max_threads:
            break

        raw_thread = zmail_call(cfg, "getThread", threadID=thread_id)
        append_jsonl(
            trace_path,
            {
                "ts": now_iso(),
                "step": "getThread",
                "thread_id": thread_id,
                "raw": raw_thread,
            },
        )
        thread_items = raw_thread.get("items", [])
        ids: list[Any] = []
        for item in thread_items:
            if isinstance(item, dict):
                message_id = item.get("messageID")
                row_id = item.get("rowID")
                ids.append(message_id if message_id else row_id)
        ids = [x for x in ids if x is not None]
        if not ids:
            continue

        raw_messages = zmail_call(cfg, "getMessages", ids=ids)
        append_jsonl(
            trace_path,
            {
                "ts": now_iso(),
                "step": "getMessages_thread_batch",
                "thread_id": thread_id,
                "ids_count": len(ids),
                "raw": raw_messages,
            },
        )
        parsed = parse_bodies(raw_messages.get("items", []))
        for message in parsed:
            bodies[message.stable_id()] = message

    return bodies


def build_answer_from_messages(messages: dict[str, MailBody]) -> tuple[MissionAnswer, list[CandidateEvidence], str | None, str | None]:
    """Builds best current answer from fetched messages plus extraction evidence.

    Selection policy:
    - For each field we gather candidates and choose the one from the highest
      relevance-scored message.
    - We keep all selected evidences to explain *why* each value was chosen.
    - We scan all messages for main/side flags to support both missions.
    """

    date_candidates: list[tuple[int, CandidateEvidence]] = []
    password_candidates: list[tuple[int, CandidateEvidence]] = []
    code_candidates: list[tuple[int, CandidateEvidence]] = []

    main_flag: str | None = None
    side_flag: str | None = None

    for msg in messages.values():
        score = score_message_relevance(msg)
        text = "\n".join([msg.subject, msg.message, msg.from_, msg.to])
        text_lower = text.lower()

        for flag in find_flags(text):
            main_flag = main_flag or flag

        if contains_side_hint(text) and main_flag:
            side_flag = side_flag or main_flag

        for code in extract_confirmation_codes(text):
            correction_boost = 5 if "poprawny" in text_lower else 0
            evidence = CandidateEvidence(
                field_name="confirmation_code",
                value=code,
                reason="Matched strict SEC-* pattern in message body.",
                message_id=msg.stable_id(),
                subject=msg.subject,
                sender=msg.from_,
                date=msg.date,
            )
            code_candidates.append((score + correction_boost, evidence))

        dates = extract_dates(text)
        if dates and ("atak" in text_lower or "bomb" in text_lower or "security" in text_lower):
            for date_value in dates:
                evidence = CandidateEvidence(
                    field_name="date",
                    value=date_value,
                    reason="Date found in attack/security context.",
                    message_id=msg.stable_id(),
                    subject=msg.subject,
                    sender=msg.from_,
                    date=msg.date,
                )
                date_candidates.append((score, evidence))

        password_match = re.search(
            r"(?:has[^\n]{0,12}|password)[^\n:]{0,80}[:=]\s*([A-Za-z0-9!@#$%^&*()_+\-]{4,})",
            text,
            flags=re.IGNORECASE,
        )
        if not password_match:
            password_match = re.search(
                r"(?:has[^\n]{0,20}|password)[^\n]{0,100}\n+\s*([A-Za-z0-9!@#$%^&*()_+\-]{4,})",
                text,
                flags=re.IGNORECASE,
            )
        if password_match:
            value = password_match.group(1).strip().rstrip(".,)")
            evidence = CandidateEvidence(
                field_name="password",
                value=value,
                reason="Password-like token matched after haslo/password marker.",
                message_id=msg.stable_id(),
                subject=msg.subject,
                sender=msg.from_,
                date=msg.date,
            )
            password_candidates.append((score, evidence))

    # Fallback for password if explicit marker did not appear.
    if not password_candidates:
        for msg in messages.values():
            text = "\n".join([msg.subject, msg.message])
            text_lower = text.lower()
            if (
                ("pracownicz" in text_lower or "system pracowniczy" in text_lower)
                and ("has" in text_lower or "password" in text_lower)
            ):
                generic = re.search(r"\b[A-Za-z0-9!@#$%^&*()_+\-]{8,}\b", text)
                if generic:
                    password_candidates.append(
                        (
                            score_message_relevance(msg),
                            CandidateEvidence(
                                field_name="password",
                                value=generic.group(0),
                                reason="Fallback token from employee/system-related message.",
                                message_id=msg.stable_id(),
                                subject=msg.subject,
                                sender=msg.from_,
                                date=msg.date,
                            ),
                        )
                    )

    evidences: list[CandidateEvidence] = []
    answer = MissionAnswer()

    if code_candidates:
        best = sorted(
            code_candidates,
            key=lambda x: (x[0], len(x[1].value), x[1].date),
            reverse=True,
        )[0][1]
        answer.confirmation_code = best.value
        evidences.append(best)
    if date_candidates:
        best = sorted(
            date_candidates,
            key=lambda x: (x[0], x[1].date, x[1].value),
            reverse=True,
        )[0][1]
        answer.date = best.value
        evidences.append(best)
    if password_candidates:
        best = sorted(
            password_candidates,
            key=lambda x: (x[0], len(x[1].value), x[1].date),
            reverse=True,
        )[0][1]
        answer.password = best.value
        evidences.append(best)

    return answer, evidences, main_flag, side_flag


def merge_answer(base: MissionAnswer, update: MissionAnswer) -> MissionAnswer:
    """Merges newly extracted values into existing answer without losing known data."""

    return MissionAnswer(
        password=update.password or base.password,
        date=update.date or base.date,
        confirmation_code=update.confirmation_code or base.confirmation_code,
    )


def is_answer_complete(answer: MissionAnswer) -> bool:
    """Checks whether all three required mission fields are already populated."""

    return bool(answer.password and answer.date and answer.confirmation_code)


def choose_selected_messages(messages: dict[str, MailBody], evidences: list[CandidateEvidence]) -> dict[str, MailBody]:
    """Returns subset of messages worth persisting as "selected" mission evidence.

    We keep messages that either:
    - directly produced an evidence item, or
    - have high relevance score (>=8), or
    - contain side quest hint phrase.
    """

    evidence_ids = {e.message_id for e in evidences}
    selected: dict[str, MailBody] = {}
    for mid, message in messages.items():
        if mid in evidence_ids or score_message_relevance(message) >= 8 or contains_side_hint(message.message):
            selected[mid] = message
    return selected


def tool_definitions() -> list[dict[str, Any]]:
    """Returns OpenAI function-calling tool definitions for mailbox mission."""

    return [
        {
            "type": "function",
            "function": {
                "name": "zmail_help",
                "description": "Call zmail help endpoint to inspect actions and params.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_inbox",
                "description": "Get inbox page metadata.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "page": {"type": "integer", "minimum": 1},
                        "per_page": {"type": "integer", "minimum": 5, "maximum": 20},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "search_mails",
                "description": "Search mailbox with Gmail-like query syntax.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "page": {"type": "integer", "minimum": 1},
                        "per_page": {"type": "integer", "minimum": 5, "maximum": 20},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_messages",
                "description": "Fetch full message body by ids (rowID or messageID, also arrays).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "ids": {
                            "oneOf": [
                                {"type": "string"},
                                {"type": "integer"},
                                {"type": "array", "items": {"oneOf": [{"type": "string"}, {"type": "integer"}]}},
                            ]
                        }
                    },
                    "required": ["ids"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_thread_messages",
                "description": "Fetch all message bodies from a thread by threadID.",
                "parameters": {
                    "type": "object",
                    "properties": {"thread_id": {"type": "integer"}},
                    "required": ["thread_id"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "extract_candidates",
                "description": "Extract current best candidates for password/date/confirmation_code from cached messages.",
                "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "verify_answer",
                "description": "Verify provided answer payload with HQ. Use exact schema values.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "password": {"type": "string"},
                        "date": {"type": "string"},
                        "confirmation_code": {"type": "string"},
                    },
                    "required": ["password", "date", "confirmation_code"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "finish",
                "description": "Finish the run and provide concise summary.",
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                },
            },
        },
    ]


def _register_headers(runtime: AgentRuntime, items: list[dict[str, Any]]) -> int:
    """Parses and caches mail headers, returning number of newly seen headers."""

    before = len(runtime.headers)
    for header in parse_headers(items):
        runtime.headers[header.stable_id()] = header
    return len(runtime.headers) - before


def _register_messages(runtime: AgentRuntime, items: list[dict[str, Any]], paths: RunPaths) -> int:
    """Parses, caches and persists full messages, returning count of new records."""

    before = len(runtime.messages)
    for message in parse_bodies(items):
        mid = message.stable_id()
        if mid not in runtime.messages:
            runtime.messages[mid] = message
            save_message_json(paths.all_messages_dir, message)
            save_message_markdown(paths.all_messages_dir, message)
    return len(runtime.messages) - before


def _tool_result(ok: bool, **kwargs: Any) -> dict[str, Any]:
    """Creates consistent tool result envelope for function-calling loop."""

    out = {"ok": ok}
    out.update(kwargs)
    return out


def normalize_ids_arg(ids: Any) -> Any:
    """Normalizes `ids` argument accepted by get_messages tool.

    Agent models sometimes return ids as comma-separated string (`"5,4,2"`).
    This helper converts it into array format required by zmail API while
    preserving already valid scalar or list inputs.
    """

    if isinstance(ids, list):
        return ids
    if isinstance(ids, (int, float)):
        return int(ids)
    if isinstance(ids, str):
        raw = ids.strip()
        if "," in raw:
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            normalized: list[Any] = []
            for part in parts:
                if part.isdigit():
                    normalized.append(int(part))
                else:
                    normalized.append(part)
            return normalized
        if raw.isdigit():
            return int(raw)
        return raw
    return ids


def execute_tool_call(
    cfg: AppConfig,
    runtime: AgentRuntime,
    paths: RunPaths,
    tool_name: str,
    args: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    """Executes one tool call and returns `(result, should_finish)` tuple."""

    if tool_name == "zmail_help":
        raw = zmail_call(cfg, "help")
        write_json(paths.run_dir / "help.json", raw)
        return _tool_result(True, raw=raw), False

    if tool_name == "get_inbox":
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", cfg.per_page))
        raw = zmail_call(cfg, "getInbox", page=page, perPage=per_page)
        added = _register_headers(runtime, raw.get("items", []))
        return _tool_result(True, page=page, per_page=per_page, headers_added=added, raw=raw), False

    if tool_name == "search_mails":
        query = str(args.get("query", "")).strip()
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", cfg.per_page))
        raw = zmail_call(cfg, "search", query=query, page=page, perPage=per_page)
        added = _register_headers(runtime, raw.get("items", []))
        return _tool_result(True, query=query, page=page, per_page=per_page, headers_added=added, raw=raw), False

    if tool_name == "get_messages":
        ids = normalize_ids_arg(args.get("ids"))
        raw = zmail_call(cfg, "getMessages", ids=ids)
        added = _register_messages(runtime, raw.get("items", []), paths)
        return _tool_result(True, ids=ids, messages_added=added, total_messages=len(runtime.messages), raw=raw), False

    if tool_name == "get_thread_messages":
        thread_id = int(args.get("thread_id"))
        thread_raw = zmail_call(cfg, "getThread", threadID=thread_id)
        ids: list[Any] = []
        for item in thread_raw.get("items", []):
            if isinstance(item, dict):
                ids.append(item.get("messageID") or item.get("rowID"))
        ids = [x for x in ids if x is not None]
        msg_raw = {"items": []}
        if ids:
            msg_raw = zmail_call(cfg, "getMessages", ids=ids)
        added = _register_messages(runtime, msg_raw.get("items", []), paths)
        return _tool_result(
            True,
            thread_id=thread_id,
            ids_count=len(ids),
            messages_added=added,
            thread_raw=thread_raw,
            raw=msg_raw,
        ), False

    if tool_name == "extract_candidates":
        # Auto-expand relevant ticket/security threads once to capture message
        # corrections (e.g. fixed confirmation code in follow-up reply).
        thread_ids_to_expand: list[int] = []
        for msg in runtime.messages.values():
            if msg.threadID is None or msg.threadID in runtime.expanded_threads:
                continue
            subject_lower = msg.subject.lower()
            sender_lower = msg.from_.lower()
            if "ticket" in subject_lower or "sec" in subject_lower or "security" in sender_lower:
                thread_ids_to_expand.append(msg.threadID)
        for thread_id in thread_ids_to_expand[: cfg.max_threads_per_round]:
            thread_raw = zmail_call(cfg, "getThread", threadID=thread_id)
            ids: list[Any] = []
            for item in thread_raw.get("items", []):
                if isinstance(item, dict):
                    ids.append(item.get("messageID") or item.get("rowID"))
            ids = [x for x in ids if x is not None]
            if ids:
                msg_raw = zmail_call(cfg, "getMessages", ids=ids)
                _register_messages(runtime, msg_raw.get("items", []), paths)
            runtime.expanded_threads.add(thread_id)

        answer, evidences, main_flag, side_flag = build_answer_from_messages(runtime.messages)
        runtime.found_flag_main = runtime.found_flag_main or main_flag
        runtime.found_flag_side = runtime.found_flag_side or side_flag
        selected = choose_selected_messages(runtime.messages, evidences)
        for message in selected.values():
            save_message_json(paths.selected_messages_dir, message)
            save_message_markdown(paths.selected_messages_dir, message, title_prefix="[SELECTED]")
        return _tool_result(
            True,
            answer=answer.model_dump(),
            evidences=[e.model_dump() for e in evidences],
            total_messages=len(runtime.messages),
            selected_messages=len(selected),
        ), False

    if tool_name == "verify_answer":
        # Trust-but-verify: model can pass malformed values, so normalize and
        # repair with best extracted candidates from cached messages.
        extracted_answer, _, _, _ = build_answer_from_messages(runtime.messages)
        supplied_password = str(args.get("password", "")).strip() or None
        supplied_date = str(args.get("date", "")).strip() or None
        supplied_code_raw = str(args.get("confirmation_code", "")).strip() or None
        supplied_code = normalize_confirmation_code(supplied_code_raw) if supplied_code_raw else None
        best_code = best_confirmation_code_from_messages(runtime.messages)

        answer = MissionAnswer(
            password=extracted_answer.password or supplied_password,
            date=extracted_answer.date or supplied_date,
            confirmation_code=best_code or extracted_answer.confirmation_code or supplied_code,
        )
        if not is_answer_complete(answer):
            return _tool_result(
                False,
                error="Cannot verify: incomplete normalized answer.",
                supplied=args,
                normalized=answer.model_dump(),
            ), False
        try:
            verify_resp = verify_call(cfg, answer)
        except Exception as exc:  # noqa: BLE001
            return _tool_result(
                False,
                error=str(exc),
                supplied=args,
                normalized=answer.model_dump(),
            ), False

        runtime.verify_feedbacks.append(verify_resp)
        verify_text = json.dumps(verify_resp, ensure_ascii=False)
        flags = find_flags(verify_text)
        if flags:
            runtime.found_flag_main = runtime.found_flag_main or flags[0]
        if contains_side_hint(verify_text) and flags:
            runtime.found_flag_side = runtime.found_flag_side or flags[0]
        return _tool_result(
            True,
            response=verify_resp,
            main_flag=runtime.found_flag_main,
            normalized=answer.model_dump(),
        ), False

    if tool_name == "finish":
        reason = str(args.get("reason", "")).strip()
        return _tool_result(True, reason=reason), True

    return _tool_result(False, error=f"Unknown tool: {tool_name}"), False


def run_solver(cfg: AppConfig, paths: RunPaths) -> dict[str, Any]:
    """Runs agent loop with function calling against OpenRouter tools."""

    log("run_solver start (agent + function calling)")
    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)
    runtime = AgentRuntime(
        headers={},
        messages={},
        verify_feedbacks=[],
        found_flag_main=None,
        found_flag_side=None,
        expanded_threads=set(),
    )

    system_prompt = (
        "You are solving task 'mailbox' using ONLY available tools. "
        "Strict workflow: (1) call zmail_help once, (2) call get_inbox page=1, (3) run searches with queries: "
        "`from:proton.me`, `to:operator04227@system.nwo`, `from:security@system.nwo`, `subject:Ticket`, `subject:SEC`, "
        "(4) fetch full messages via get_messages/get_thread_messages, "
        "(5) call extract_candidates, (6) verify_answer, (7) iterate if needed because mailbox is active. "
        "Never guess values without message evidence. "
        "confirmation_code must match SEC- + 28 chars. "
        "Use short tool budgets and stop when main flag appears. "
        "Do not prioritize side quest before primary mission."
    )
    user_prompt = (
        "Find date, password, confirmation_code for mailbox task. "
        "Use Gmail-like operators, fetch full bodies, verify iteratively. "
        "Watch for side hint: 'Mam wiadomość! No nareszcie!'."
    )
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    finished = False
    for step in range(1, cfg.max_agent_steps + 1):
        log(f"agent step {step}/{cfg.max_agent_steps}")
        completion = client.chat.completions.create(
            model=cfg.llm_model,
            temperature=0,
            messages=messages,
            tools=tool_definitions(),
            tool_choice="auto",
        )
        assistant = completion.choices[0].message
        append_jsonl(
            paths.llm_trace_jsonl,
            {"ts": now_iso(), "step": step, "assistant": assistant.model_dump(exclude_none=True)},
        )

        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if assistant.content:
            assistant_msg["content"] = assistant.content
        if assistant.tool_calls:
            assistant_msg["tool_calls"] = [tc.model_dump(exclude_none=True) for tc in assistant.tool_calls]
        messages.append(assistant_msg)

        tool_calls = assistant.tool_calls or []
        if not tool_calls:
            log("agent returned no tool calls, continuing")
            if runtime.found_flag_main:
                break
            continue

        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            log(f"tool call: {tc.function.name} args={args}")
            try:
                result, should_finish = execute_tool_call(cfg, runtime, paths, tc.function.name, args)
            except Exception as exc:  # noqa: BLE001
                result, should_finish = _tool_result(False, error=str(exc), tool_name=tc.function.name), False
            append_jsonl(
                paths.logs_jsonl,
                {
                    "ts": now_iso(),
                    "step": "tool_call",
                    "tool_name": tc.function.name,
                    "args": args,
                    "result": result,
                },
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
            if should_finish:
                finished = True
                break
            if runtime.found_flag_main:
                finished = True
                break
        if finished:
            break
        if cfg.poll_seconds > 0:
            time.sleep(cfg.poll_seconds)

    answer, evidences, _, _ = build_answer_from_messages(runtime.messages)
    selected = choose_selected_messages(runtime.messages, evidences)
    for message in selected.values():
        save_message_json(paths.selected_messages_dir, message)
        save_message_markdown(paths.selected_messages_dir, message, title_prefix="[SELECTED]")

    return {
        "ok": runtime.found_flag_main is not None,
        "task": cfg.task_name,
        "model": cfg.llm_model,
        "answer": answer.model_dump(),
        "flag_main": runtime.found_flag_main,
        "flag_side": runtime.found_flag_side,
        "verify_feedbacks": runtime.verify_feedbacks,
        "output_dir": str(paths.run_dir),
        "headers_total": len(runtime.headers),
        "messages_total": len(runtime.messages),
        "selected_messages_total": len(selected),
        "evidences": [e.model_dump() for e in evidences],
    }


def parse_args() -> argparse.Namespace:
    """Parses CLI arguments controlling mission run behavior."""

    parser = argparse.ArgumentParser(description="Season2 mailbox mission solver.")
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=None,
        help="Override MAILBOX_MAX_ROUNDS for this run.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=None,
        help="Override MAILBOX_POLL_SECONDS for this run.",
    )
    return parser.parse_args()


def main() -> None:
    """Program entrypoint: loads config, runs solver, writes final artifacts.

    This function only orchestrates initialization and result persistence. All
    mission logic remains in dedicated functions to keep responsibilities clear.
    """

    base_dir = Path(__file__).resolve().parent
    season2_dir = base_dir.parent
    project_root = season2_dir.parent

    setup_environment(project_root=project_root, season2_dir=season2_dir)
    cfg = build_config(base_dir=base_dir)

    args = parse_args()
    if args.max_rounds is not None:
        cfg = cfg.model_copy(update={"max_rounds": args.max_rounds})
    if args.poll_seconds is not None:
        cfg = cfg.model_copy(update={"poll_seconds": args.poll_seconds})

    clear_output_root(cfg.output_dir)
    log(f"cleared output root: {cfg.output_dir}")
    paths = init_run_paths(cfg.output_dir)
    write_json(paths.run_dir / "config.json", cfg.model_dump(mode="json"))
    log(f"run directory: {paths.run_dir}")
    log(
        "config: "
        f"max_rounds={cfg.max_rounds}, poll_seconds={cfg.poll_seconds}, per_page={cfg.per_page}, "
        f"model={cfg.llm_model}, openrouter_base={cfg.openrouter_base_url}"
    )

    try:
        result = run_solver(cfg, paths)
    except Exception as exc:  # noqa: BLE001
        log(f"fatal error: {exc}")
        result = {
            "ok": False,
            "task": cfg.task_name,
            "error": str(exc),
            "output_dir": str(paths.run_dir),
        }
        append_jsonl(paths.logs_jsonl, {"ts": now_iso(), "step": "fatal", "error": str(exc)})

    write_json(paths.result_json, result)
    log(f"run finished: ok={result.get('ok')} output={result.get('output_dir')}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
