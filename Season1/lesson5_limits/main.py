"""Simple CLI entry point for the railway task."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    from .config import AppSettings
    from .railway_client import call_railway_action
except ImportError:
    from config import AppSettings
    from railway_client import call_railway_action


def _find_flag(payload: dict[str, Any]) -> str | None:
    """Return flag value if payload contains `{FLG:...}` pattern."""

    blob = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"\{FLG:[^}]+\}", blob)
    return match.group(0) if match else None


def _save_response(payload: dict[str, Any], *, output_path: Path) -> None:
    """Save JSON payload to disk for later inspection."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _call_and_print(
    *,
    settings: AppSettings,
    action: str,
    route: str | None = None,
    value: str | None = None,
) -> tuple[dict[str, Any], str | None]:
    """Execute one action, print JSON response, and return optional flag."""

    kwargs: dict[str, Any] = {}
    if route is not None:
        kwargs["route"] = route
    if value is not None:
        kwargs["value"] = value

    response_model = call_railway_action(
        api_key=settings.api_key,
        action=action,
        settings=settings,
        **kwargs,
    )
    response = response_model.model_dump()
    print(f"\n=== ACTION: {action} ===")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    return response, _find_flag(response)


def main() -> None:
    """Run the full action sequence required to activate route X-01."""

    settings = AppSettings()
    routes = ["X-01", "x-01"]
    output_path = Path("lesson5_limits") / "output" / "verify_response.json"
    latest_response: dict[str, Any] = {}

    help_response, flag = _call_and_print(settings=settings, action="help")
    latest_response = help_response
    _save_response(latest_response, output_path=output_path)
    if flag:
        print(f"\nFLAG FOUND: {flag}")
        print(f"Saved response to: {output_path}")
        return
    if help_response.get("ok") is False:
        print("\nWarning: help returned ok=false. Continuing anyway.")

    for route in routes:
        print(f"\n######## ROUTE TRY: {route} ########")
        steps: list[dict[str, str]] = [
            {"action": "getstatus"},
            {"action": "reconfigure"},
            {"action": "setstatus", "value": "RTOPEN"},
            {"action": "save"},
            {"action": "getstatus"},
        ]

        for step in steps:
            action = step["action"]
            value = step.get("value")
            response, flag = _call_and_print(
                settings=settings,
                action=action,
                route=route,
                value=value,
            )
            latest_response = response
            _save_response(latest_response, output_path=output_path)
            if flag:
                print(f"\nFLAG FOUND: {flag}")
                print(f"Saved response to: {output_path}")
                return

            if response.get("ok") is False:
                print("\nWarning: API returned ok=false for this step. Continuing to next step.")

    print("\nSequence completed for all route variants. No flag found in responses.")
    print(f"Saved latest response to: {output_path}")


if __name__ == "__main__":
    main()
