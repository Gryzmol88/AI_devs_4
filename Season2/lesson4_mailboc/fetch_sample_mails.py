import argparse
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib import error, request

API_URL = "https://hub.ag3nts.org/api/zmail"


def load_env(path: Path) -> dict:
    data = {}
    if not path.exists():
        return data
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def post_json(payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        API_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw)
    except error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {details}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def normalize_for_filename(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", value)
    return cleaned[:80] if cleaned else "message"


def save_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def extract_items(search_response: dict) -> list[dict]:
    items = search_response.get("items")
    if isinstance(items, list):
        return [x for x in items if isinstance(x, dict)]
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Pobierz próbki maili z zmail i zapisz na dysk.")
    parser.add_argument("--query", default="from:proton.me", help="Zapytanie search (jak w Gmail)")
    parser.add_argument("--max-messages", type=int, default=8, help="Maksymalna liczba maili do zapisania")
    parser.add_argument("--page", type=int, default=1, help="Numer strony dla help/getInbox/search")
    parser.add_argument("--per-page", type=int, default=20, help="Liczba rekordów na stronę (5-20)")
    parser.add_argument("--out-dir", default="output", help="Katalog wyjściowy")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent
    env_values = load_env(project_root / ".env")
    api_key = os.getenv("HUB_API_KEY") or env_values.get("HUB_API_KEY")

    if not api_key:
        raise SystemExit("Brak HUB_API_KEY w ENV lub .env")

    run_dir = script_dir / args.out_dir / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    print("[1/4] Fetch: help")
    help_resp = post_json({"apikey": api_key, "action": "help", "page": args.page})
    save_json(run_dir / "help.json", help_resp)

    print("[2/4] Fetch: getInbox")
    inbox_resp = post_json(
        {
            "apikey": api_key,
            "action": "getInbox",
            "page": args.page,
            "perPage": max(5, min(20, args.per_page)),
        }
    )
    save_json(run_dir / "inbox_page1.json", inbox_resp)

    print(f"[3/4] Fetch: search query='{args.query}'")
    search_resp = post_json(
        {
            "apikey": api_key,
            "action": "search",
            "query": args.query,
            "page": args.page,
            "perPage": max(5, min(20, args.per_page)),
        }
    )
    save_json(run_dir / "search.json", search_resp)

    items = extract_items(search_resp)
    if not items:
        print("Brak wyników search - zapisano tylko help/inbox/search.")
        return

    print(f"[4/4] Fetch details for up to {args.max_messages} messages")
    samples = []
    for idx, item in enumerate(items[: args.max_messages], start=1):
        message_id = item.get("messageID")
        row_id = item.get("rowID")
        ids = message_id or row_id
        if not ids:
            continue

        detail_resp = post_json({"apikey": api_key, "action": "getMessages", "ids": ids})
        record = {
            "search_item": item,
            "message_details": detail_resp,
        }
        samples.append(record)

        safe_name = normalize_for_filename(str(message_id or row_id))
        save_json(run_dir / f"message_{idx:02d}_{safe_name}.json", record)

    save_json(run_dir / "sample_messages.json", {"query": args.query, "samples": samples})
    print(f"Zapisano próbki maili w: {run_dir}")


if __name__ == "__main__":
    main()
