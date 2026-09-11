from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urlerror
from urllib import request as urlrequest

ZMAIL_URL = "https://hub.ag3nts.org/api/zmail"
SIDE_HINT_PATTERNS = [
    "mam wiadomość",
    "mam wiadomosc",
    "no nareszcie",
    "nareszcie",
]


def now_iso() -> str:
    """Returns ISO timestamp for logs and file metadata."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Prints a timestamped console log line."""

    print(f"[{now_iso()}] {message}")


def load_env_file(path: Path) -> None:
    """Loads simple KEY=VALUE pairs from .env into process env.

    Existing variables are not overridden.
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


def post_json(url: str, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    """Sends JSON POST request and returns decoded JSON response."""

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
    """Converts arbitrary id text to safe filename fragment."""

    cleaned = re.sub(r"[^a-zA-Z0-9._-]", "_", value)
    cleaned = cleaned.strip("_")
    return cleaned[:120] if cleaned else "message"


def write_json(path: Path, payload: Any) -> None:
    """Writes pretty JSON to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Appends one JSON record per line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_text(value: str) -> str:
    """Normalizes text for robust matching (case-insensitive, no diacritics)."""

    lower = value.lower()
    decomposed = unicodedata.normalize("NFKD", lower)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def detect_side_hint_matches(subject: str, body: str) -> list[str]:
    """Returns matched side-hint patterns found in subject/body text."""

    haystack = normalize_text(f"{subject}\n{body}")
    matched: list[str] = []
    for pattern in SIDE_HINT_PATTERNS:
        if normalize_text(pattern) in haystack:
            matched.append(pattern)
    return matched


def parse_args() -> argparse.Namespace:
    """Parses CLI args for mailbox watcher."""

    parser = argparse.ArgumentParser(description="Nasłuch nowych maili i zapis na dysk.")
    parser.add_argument("--interval", type=float, default=10.0, help="Czas między cyklami (sekundy).")
    parser.add_argument("--pages", type=int, default=4, help="Ile stron inbox sprawdzać w każdym cyklu.")
    parser.add_argument("--per-page", type=int, default=20, help="Rozmiar strony inbox (5-20).")
    parser.add_argument("--timeout", type=int, default=60, help="Timeout requestów HTTP (sekundy).")
    parser.add_argument(
        "--cooldown-429",
        type=float,
        default=30.0,
        help="Dodatkowa pauza po błędzie 429 (sekundy).",
    )
    parser.add_argument(
        "--skip-history",
        action="store_true",
        help="Nie pobieraj istniejącej historii na starcie; zapisuj tylko wiadomości przychodzące po uruchomieniu.",
    )
    return parser.parse_args()


def main() -> None:
    """Runs infinite polling loop for inbox and saves newly arrived messages.

    Workflow:
    1. Load env from project and Season2 folders.
    2. Poll getInbox pages and collect message IDs.
    3. Compare with local seen state.
    4. Fetch full bodies of newly detected messages via getMessages.
    5. Save each new message to output/messages and append to log.
    """

    args = parse_args()

    base_dir = Path(__file__).resolve().parent
    season2_dir = base_dir.parent
    project_root = season2_dir.parent

    load_env_file(project_root / ".env")
    load_env_file(season2_dir / ".env")

    api_key = os.getenv("HUB_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("Brak HUB_API_KEY w env (.env lub Season2/.env)")

    output_dir = base_dir / "output"
    messages_dir = output_dir / "messages"
    state_path = output_dir / "state.json"
    log_path = output_dir / "watcher_log.jsonl"
    hints_path = output_dir / "hint_matches.jsonl"

    output_dir.mkdir(parents=True, exist_ok=True)
    messages_dir.mkdir(parents=True, exist_ok=True)

    state: dict[str, Any] = {"seen_ids": [], "last_cycle": None}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:
            state = {"seen_ids": [], "last_cycle": None}

    seen_ids = set(state.get("seen_ids", []))
    stop_requested = False
    consecutive_429 = 0

    def _handle_stop(signum: int, frame: Any) -> None:  # noqa: ARG001
        nonlocal stop_requested
        stop_requested = True
        log("Stop signal received, finishing current cycle...")

    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    log("Mailbox watcher started")
    log(f"output: {output_dir}")
    log(
        f"interval={args.interval}s pages={args.pages} per_page={args.per_page} "
        f"timeout={args.timeout}s cooldown_429={args.cooldown_429}s"
    )

    # Optional mode: treat current mailbox as already known.
    if args.skip_history and not seen_ids:
        try:
            bootstrap_ids: set[str] = set()
            for page in range(1, max(1, args.pages) + 1):
                raw = post_json(
                    ZMAIL_URL,
                    {
                        "apikey": api_key,
                        "action": "getInbox",
                        "page": page,
                        "perPage": max(5, min(20, args.per_page)),
                    },
                    args.timeout,
                )
                for item in raw.get("items", []):
                    if isinstance(item, dict):
                        mid = item.get("messageID")
                        if isinstance(mid, str) and mid:
                            bootstrap_ids.add(mid)
            seen_ids.update(bootstrap_ids)
            log(f"skip-history: marked existing messages as seen ({len(bootstrap_ids)})")
        except Exception as exc:
            log(f"skip-history bootstrap failed: {exc}")

    cycle_no = 0
    while not stop_requested:
        cycle_no += 1
        cycle_start = now_iso()
        try:
            headers: dict[str, dict[str, Any]] = {}
            for page in range(1, max(1, args.pages) + 1):
                inbox_raw = post_json(
                    ZMAIL_URL,
                    {
                        "apikey": api_key,
                        "action": "getInbox",
                        "page": page,
                        "perPage": max(5, min(20, args.per_page)),
                    },
                    args.timeout,
                )
                append_jsonl(
                    log_path,
                    {
                        "ts": now_iso(),
                        "step": "getInbox",
                        "cycle": cycle_no,
                        "page": page,
                        "count": len(inbox_raw.get("items", [])),
                    },
                )
                for item in inbox_raw.get("items", []):
                    if not isinstance(item, dict):
                        continue
                    mid = item.get("messageID")
                    if isinstance(mid, str) and mid:
                        headers[mid] = item

                pagination = inbox_raw.get("pagination", {})
                total_pages = pagination.get("totalPages")
                if isinstance(total_pages, int) and page >= total_pages:
                    break

            current_ids = set(headers.keys())
            new_ids = sorted(current_ids - seen_ids)
            log(f"cycle={cycle_no} total_visible={len(current_ids)} new={len(new_ids)}")

            if new_ids:
                # API accepts list in `ids`.
                details_raw = post_json(
                    ZMAIL_URL,
                    {"apikey": api_key, "action": "getMessages", "ids": new_ids},
                    args.timeout,
                )
                items = details_raw.get("items", [])

                saved = 0
                for message in items:
                    if not isinstance(message, dict):
                        continue
                    mid = str(message.get("messageID") or "")
                    if not mid:
                        continue
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    stem = f"{ts}_{safe_filename(mid)}"
                    write_json(messages_dir / f"{stem}.json", message)

                    md = (
                        f"# {message.get('subject', '')}\n\n"
                        f"- id: `{mid}`\n"
                        f"- from: `{message.get('from', '')}`\n"
                        f"- to: `{message.get('to', '')}`\n"
                        f"- date: `{message.get('date', '')}`\n\n"
                        "## Body\n\n"
                        f"{message.get('message', '')}\n"
                    )
                    (messages_dir / f"{stem}.md").write_text(md, encoding="utf-8")
                    saved += 1
                    log(
                        "NEW MAIL "
                        f"id={mid} from={message.get('from', '')} "
                        f"date={message.get('date', '')} "
                        f"subject={message.get('subject', '')}"
                    )
                    matches = detect_side_hint_matches(
                        subject=str(message.get("subject", "")),
                        body=str(message.get("message", "")),
                    )
                    if matches:
                        log(
                            "HINT MATCH "
                            f"id={mid} patterns={matches} "
                            f"subject={message.get('subject', '')}"
                        )
                        append_jsonl(
                            hints_path,
                            {
                                "ts": now_iso(),
                                "messageID": mid,
                                "from": message.get("from", ""),
                                "date": message.get("date", ""),
                                "subject": message.get("subject", ""),
                                "matched_patterns": matches,
                            },
                        )

                append_jsonl(
                    log_path,
                    {
                        "ts": now_iso(),
                        "step": "getMessages",
                        "cycle": cycle_no,
                        "requested": len(new_ids),
                        "saved": saved,
                        "ids": new_ids,
                    },
                )
                log(f"saved {saved} new messages")
                seen_ids.update(new_ids)
            else:
                log("NO NEW MAILS in this cycle")

            state = {
                "seen_ids": sorted(seen_ids),
                "last_cycle": {
                    "cycle": cycle_no,
                    "started_at": cycle_start,
                    "finished_at": now_iso(),
                    "visible_count": len(current_ids),
                    "new_count": len(new_ids),
                },
            }
            write_json(state_path, state)

        except Exception as exc:
            append_jsonl(
                log_path,
                {
                    "ts": now_iso(),
                    "step": "cycle_error",
                    "cycle": cycle_no,
                    "error": str(exc),
                },
            )
            log(f"cycle error: {exc}")
            err_text = str(exc)
            if "HTTP 429" in err_text or "Za często wykonujesz zapytania" in err_text:
                consecutive_429 += 1
                cooldown = max(1.0, args.cooldown_429) * min(consecutive_429, 4)
                log(f"rate limit detected, sleeping {cooldown:.1f}s before next cycle")
                time.sleep(cooldown)
                continue
            consecutive_429 = 0

        if stop_requested:
            break
        consecutive_429 = 0
        time.sleep(max(0.2, args.interval))

    log("Watcher stopped")
    write_json(
        state_path,
        {
            "seen_ids": sorted(seen_ids),
            "last_cycle": {
                "cycle": cycle_no,
                "finished_at": now_iso(),
                "stopped": True,
            },
        },
    )


if __name__ == "__main__":
    main()
