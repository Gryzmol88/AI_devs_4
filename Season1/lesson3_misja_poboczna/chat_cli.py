from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import requests
from dotenv import load_dotenv


def load_env() -> None:
    """Load .env from common project locations."""
    base = Path(__file__).resolve().parent
    season1 = base.parent
    project = season1.parent
    for path in (base / ".env", season1 / ".env", project / ".env"):
        if path.exists():
            load_dotenv(path, override=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="Interaktywny czat z endpointem operatora (POST /, body: sessionID+msg)."
    )
    parser.add_argument(
        "--url",
        default=os.getenv("PROXY_URL", "http://127.0.0.1:3000/"),
        help="URL endpointu operatora, np. http://127.0.0.1:3000/ albo URL ngrok.",
    )
    parser.add_argument(
        "--session-id",
        default="manual-chat-001",
        help="Id sesji przekazywane jako sessionID.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout requestu HTTP w sekundach.",
    )
    return parser.parse_args()


def normalize_url(url: str) -> str:
    """Ensure URL ends with slash."""
    return url if url.endswith("/") else f"{url}/"


def send_message(url: str, session_id: str, msg: str, timeout: int) -> str:
    """Send one message to operator endpoint and return response text."""
    payload = {"sessionID": session_id, "msg": msg}
    response = requests.post(
        url,
        json=payload,
        timeout=timeout,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    response.raise_for_status()
    data = response.json()
    return str(data.get("msg", ""))


def main() -> None:
    """Run interactive terminal loop for chatting with operator endpoint."""
    load_env()
    args = parse_args()
    url = normalize_url(args.url)

    print(f"Target URL: {url}")
    print(f"Session ID: {args.session_id}")
    print("Wpisz pytanie i nacisnij Enter. Koniec: /exit")

    while True:
        try:
            user_msg = input("\nTy> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nKoniec.")
            break

        if not user_msg:
            continue
        if user_msg.lower() in {"/exit", "exit", "quit", "/quit"}:
            print("Koniec.")
            break

        try:
            reply = send_message(url, args.session_id, user_msg, args.timeout)
            print(f"Operator> {reply}")
        except Exception as error:  # noqa: BLE001
            details = {"error": str(error)}
            print(f"Operator> [ERROR] {json.dumps(details, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
