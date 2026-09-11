"""Bootstrap for side quest: do not block for long rate-limit windows."""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import requests

try:
    from .config import SideQuestSettings
    from .models import RailwayAnswer, RailwayRequest, RunState
    from .state_store import load_state, save_state
except ImportError:
    from config import SideQuestSettings
    from models import RailwayAnswer, RailwayRequest, RunState
    from state_store import load_state, save_state


def _find_flag(payload: dict[str, Any]) -> str | None:
    """Extract `{FLG:...}` string if present in response payload."""

    blob = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"\{FLG:[^}]+\}", blob)
    return match.group(0) if match else None


def _is_main_flag(flag: str) -> bool:
    """Return True if flag is the known main-task flag."""

    return flag.strip() == "{FLG:COUNTRYROADS}"


def _run_aggressive_mode(settings: SideQuestSettings) -> None:
    """Run side-quest probing loop without waiting for rate-limit reset."""

    output_dir = Path("lesson5_misja_poboczna") / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "aggressive_log.jsonl"

    for attempt in range(1, settings.AGGRESSIVE_MAX_ATTEMPTS + 1):
        status_code, headers, body = _post_action(
            settings=settings,
            action=settings.AGGRESSIVE_ACTION,
            route=settings.AGGRESSIVE_ROUTE,
        )
        flag = _find_flag(body)

        row = {
            "attempt": attempt,
            "status_code": status_code,
            "action": settings.AGGRESSIVE_ACTION,
            "route": settings.AGGRESSIVE_ROUTE,
            "headers": headers,
            "body": body,
            "flag": flag,
        }
        with log_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")

        print(
            f"[aggressive] attempt={attempt} status={status_code} "
            f"retry_after={headers.get('Retry-After')} violations={headers.get('X-RateLimit-Violations')}"
        )

        if flag and not _is_main_flag(flag):
            print(f"SIDEQUEST FLAG FOUND: {flag}")
            print(json.dumps(row, ensure_ascii=False, indent=2))
            return

        if flag and _is_main_flag(flag):
            print(f"MAIN FLAG SEEN: {flag}")

        time.sleep(max(0.0, settings.AGGRESSIVE_DELAY_SECONDS))

    print("Aggressive mode finished without side-quest flag.")
    print(f"Logs saved to: {log_path}")


def _seconds_from_retry_headers(headers: dict[str, str]) -> float:
    """Read wait duration from `Retry-After` or rate-limit reset headers."""

    retry_after = headers.get("Retry-After")
    if retry_after:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            return 0.0

    remaining = headers.get("X-RateLimit-Remaining") or headers.get("RateLimit-Remaining")
    reset = headers.get("X-RateLimit-Reset") or headers.get("RateLimit-Reset")
    if not remaining or not reset:
        return 0.0
    try:
        if int(float(remaining)) > 0:
            return 0.0
        reset_value = float(reset)
    except ValueError:
        return 0.0
    now_epoch = time.time()
    if reset_value > now_epoch + 1:
        return max(0.0, reset_value - now_epoch)
    return max(0.0, reset_value)


def _post_action(
    *,
    settings: SideQuestSettings,
    action: str,
    route: str | None = None,
    value: str | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    """Send single action request and return status, headers, and JSON/body."""

    answer = RailwayAnswer(action=action, route=route, value=value)
    payload = RailwayRequest(apikey=settings.api_key, answer=answer).model_dump(exclude_none=True)
    response = requests.post(settings.VERIFY_URL, json=payload, timeout=settings.REQUEST_TIMEOUT_SECONDS)
    headers = dict(response.headers)
    try:
        body: dict[str, Any] = response.json()
    except Exception:
        body = {"raw_text": response.text}
    return response.status_code, headers, body


def _call_with_short_retry(
    *,
    settings: SideQuestSettings,
    action: str,
    route: str | None = None,
    value: str | None = None,
) -> tuple[int, dict[str, str], dict[str, Any]]:
    """Retry only short transient failures to avoid long foreground waits."""

    attempts = max(1, settings.RETRIES_ON_503)
    for attempt in range(1, attempts + 1):
        status_code, headers, body = _post_action(
            settings=settings,
            action=action,
            route=route,
            value=value,
        )
        if status_code != 503 or attempt == attempts:
            return status_code, headers, body
        delay = (0.8 * attempt) + random.uniform(0.0, 0.3)
        time.sleep(delay)
    return status_code, headers, body


def main() -> None:
    """Run one short batch and checkpoint when wait would be too long."""

    parser = argparse.ArgumentParser(description="Railway side quest helper.")
    parser.add_argument(
        "--mode",
        choices=["resume", "aggressive"],
        default="resume",
        help="resume: checkpoint flow, aggressive: no waiting and fast probing",
    )
    args = parser.parse_args()

    settings = SideQuestSettings()

    if args.mode == "aggressive":
        _run_aggressive_mode(settings)
        return

    output_dir = Path("lesson5_misja_poboczna") / "output"
    state_path = output_dir / "state.json"
    state = load_state(state_path)

    steps: list[dict[str, str | None]] = [
        {"action": "help", "route": None, "value": None},
        {"action": "reconfigure", "route": state.route, "value": None},
        {"action": "setstatus", "route": state.route, "value": "RTOPEN"},
        {"action": "save", "route": state.route, "value": None},
        {"action": "getstatus", "route": state.route, "value": None},
    ]

    # If previous run already told us to wait, do not hit API too early again.
    if state.next_allowed_at is not None:
        now_utc = datetime.now(UTC)
        if now_utc < state.next_allowed_at:
            print(
                "Too early to resume. "
                f"Resume after: {state.next_allowed_at.isoformat()}"
            )
            return

    if state.step_index >= len(steps):
        if state.found_flag:
            print(f"FLAG FOUND: {state.found_flag}")
            if state.flag_source:
                print("FLAG SOURCE:")
                print(json.dumps(state.flag_source, ensure_ascii=False, indent=2))
            else:
                print("FLAG SOURCE: not saved in this state (legacy run).")
            return
        if state.main_flag:
            print(f"MAIN FLAG FOUND: {state.main_flag}")
            if state.main_flag_source:
                print("MAIN FLAG SOURCE:")
                print(json.dumps(state.main_flag_source, ensure_ascii=False, indent=2))
            print("No side-quest flag found in executed steps.")
            return
        print("All steps already executed. Reset state.json to run again.")
        return

    for idx in range(state.step_index, len(steps)):
        step = steps[idx]
        action = str(step["action"])
        route = step["route"]
        value = step["value"]

        status_code, headers, body = _call_with_short_retry(
            settings=settings,
            action=action,
            route=route,
            value=value,
        )
        state.last_response = {
            "action": action,
            "status_code": status_code,
            "headers": headers,
            "body": body,
        }
        flag = _find_flag(body)
        if flag:
            source = {
                "action": action,
                "status_code": status_code,
                "headers": headers,
                "body": body,
            }
            if _is_main_flag(flag):
                state.main_flag = flag
                state.main_flag_source = source
                print(f"MAIN FLAG FOUND: {flag}")
                print("MAIN FLAG SOURCE:")
                print(json.dumps(source, ensure_ascii=False, indent=2))
                # Continue execution to search for side-quest flag.
            else:
                state.step_index = idx + 1
                state.found_flag = flag
                state.next_allowed_at = None
                state.flag_source = source
                save_state(state_path, state)
                print(f"FLAG FOUND: {flag}")
                print("FLAG SOURCE:")
                print(json.dumps(state.flag_source, ensure_ascii=False, indent=2))
                return

        wait_seconds = _seconds_from_retry_headers(headers)
        if status_code == 429:
            state.next_allowed_at = datetime.now(UTC) + timedelta(seconds=wait_seconds)
            # Keep same step index because this step has not been completed yet.
            save_state(state_path, state)
            if wait_seconds > settings.MAX_LOCAL_WAIT_SECONDS:
                print(
                    "Long wait detected. State saved. "
                    f"Resume after: {state.next_allowed_at.isoformat()}"
                )
                return
            time.sleep(wait_seconds)
            continue

        if status_code >= 500:
            # Keep same step index. Caller can run again later.
            save_state(state_path, state)
            print(f"Transient server error on action={action}. Status={status_code}.")
            return

        if status_code >= 400:
            # Keep same step index for non-retryable client errors as well.
            save_state(state_path, state)
            print(f"Action failed with status={status_code}. Fix input or run again.")
            print(json.dumps(body, ensure_ascii=False, indent=2))
            return

        # Step completed (non-429 and non-5xx), so we can advance pointer.
        state.step_index = idx + 1
        state.next_allowed_at = None
        save_state(state_path, state)
        print(f"ACTION={action} status={status_code}")
        print(json.dumps(body, ensure_ascii=False, indent=2))

    save_state(state_path, state)
    if state.main_flag and not state.found_flag:
        print("Sequence completed. Main flag observed, but no side-quest flag found.")
        return
    print("Sequence completed without flag in this run.")


if __name__ == "__main__":
    main()
