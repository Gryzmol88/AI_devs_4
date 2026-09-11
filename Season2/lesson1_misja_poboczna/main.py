from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HINT_ORDER = ["J", "D", "I", "B", "A", "C", "G", "E", "H", "F"]
EXPECTED_KEYS = [chr(code) for code in range(ord("A"), ord("J") + 1)]
ITEM_LABELS = EXPECTED_KEYS.copy()
VERIFY_STEP_RE = re.compile(r"VERIFY_ITEM_(\d+)_ID_(.+)")
LETTER_MARKER_RE = re.compile(r"\b([A-J])\b")
PROMPT_LABEL_RE = re.compile(r"\bL:([A-J])\b")
FLAG_RE = re.compile(r"\{FLG:[^}]+\}")
DEFAULT_VERIFY_URL = "https://hub.ag3nts.org/verify"
DEFAULT_PROMPT_TEMPLATE = (
    "ID:{id}. Desc:{description}. "
    "Return DNG only for explicit weapon/attack device. "
    "Return NEU for ordinary industrial/electrical/mechanical parts "
    "and all reactor parts/components/fuel cassettes. "
    "Reply DNG or NEU."
)


def parse_args() -> argparse.Namespace:
    """Parses CLI arguments for side-quest reordering."""

    parser = argparse.ArgumentParser(
        description=(
            "Mission helper for Season2 lesson1 side quest. "
            "Takes A..J solved values and reorders them using hint: J-D-I-B-A-C-G-E-H-F."
        )
    )
    parser.add_argument(
        "--values",
        nargs=10,
        metavar="VAL",
        help="Ten solved values in order A B C D E F G H I J.",
    )
    parser.add_argument(
        "--input-json",
        type=Path,
        help="Path to JSON mapping, e.g. {\"A\":\"...\",\"B\":\"...\",...,\"J\":\"...\"}.",
    )
    parser.add_argument(
        "--input-text",
        type=Path,
        help="Path to text file with lines like: A=..., B=..., ..., J=....",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "output" / "result.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "lesson1_kontekst" / "output" / "api_trace.jsonl",
        help="Path to lesson1_kontekst api_trace.jsonl.",
    )
    parser.add_argument(
        "--value-source",
        choices=["id", "output", "message", "status_code"],
        default="id",
        help="Value extracted per VERIFY item when auto-loading from trace.",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Submit generated candidates to central /verify and stop on first flag.",
    )
    parser.add_argument(
        "--apikey",
        help="API key for /verify. If omitted, loaded from env: HUB_API_KEY or API_KEY.",
    )
    parser.add_argument(
        "--task",
        help="Task name for /verify. If omitted, SIDEQUEST_TASK_NAME or CATEGORIZE_TASK_NAME or categorize.",
    )
    parser.add_argument(
        "--verify-url",
        default=DEFAULT_VERIFY_URL,
        help="Verification endpoint URL.",
    )
    parser.add_argument(
        "--cycle-log",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "lesson1_kontekst" / "output" / "cycle_log.jsonl",
        help="Path to lesson1_kontekst cycle_log.jsonl.",
    )
    parser.add_argument(
        "--submit-mode",
        choices=["variants", "replay_order"],
        default="replay_order",
        help="Submission strategy: payload variants or replaying 10 prompts in hint order.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=30,
        help="HTTP timeout for verify calls.",
    )
    parser.add_argument(
        "--csv-url",
        help=(
            "CSV source URL. Default: CATEGORIZE_CSV_URL/ITEMS_CSV_URL "
            "or https://hub.ag3nts.org/data/{apikey}/categorize.csv"
        ),
    )
    parser.add_argument(
        "--prompt-template-file",
        type=Path,
        default=None,
        help="JSON file with prompt template field `template` (from lesson1_kontekst).",
    )
    parser.add_argument(
        "--prompt-template",
        help="Prompt template override with placeholders {label}, {id}, {description}.",
    )
    return parser.parse_args()


def load_mapping_from_json(path: Path) -> dict[str, str]:
    """Loads A..J mapping from a JSON file."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("input-json must be a JSON object.")
    return {str(key).strip().upper(): str(value) for key, value in payload.items()}


def load_env_file(env_path: Path) -> None:
    """Loads KEY=VALUE pairs from .env file into process environment."""

    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_mapping_from_text(path: Path) -> dict[str, str]:
    """Loads A..J mapping from text lines in KEY=VALUE format."""

    mapping: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        mapping[key.strip().upper()] = value.strip()
    return mapping


def build_mapping_from_values(values: list[str]) -> dict[str, str]:
    """Builds A..J mapping from a list that is already ordered A..J."""

    if len(values) != 10:
        raise ValueError("Expected exactly 10 values for A..J.")
    return {key: value for key, value in zip(EXPECTED_KEYS, values)}


def _extract_verify_index_and_id(step: str) -> tuple[int, str] | None:
    """Parses VERIFY step name and returns its ordinal index and item identifier."""

    match = VERIFY_STEP_RE.fullmatch(step.strip())
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def _pick_auto_value(entry: dict[str, Any], source: str, fallback_id: str) -> str:
    """Picks one value from verify trace entry according to requested source."""

    response_body = entry.get("response_body") or {}
    debug = response_body.get("debug") or {}

    if source == "id":
        return fallback_id
    if source == "output":
        return str(debug.get("output", ""))
    if source == "message":
        return str(response_body.get("message", ""))
    return str(entry.get("status_code", ""))


def _find_letter_markers(entry: dict[str, Any]) -> list[str]:
    """Extracts potential A..J markers from one verify response payload."""

    payload = json.dumps(entry.get("response_body") or {}, ensure_ascii=False)
    return [match.group(1) for match in LETTER_MARKER_RE.finditer(payload)]


def _extract_prompt_label(entry: dict[str, Any]) -> str | None:
    """Extracts label marker L:A..J from verify request prompt when present."""

    request_body = entry.get("request_body") or {}
    answer = request_body.get("answer") or {}
    prompt = str(answer.get("prompt") or "")
    match = PROMPT_LABEL_RE.search(prompt)
    return match.group(1) if match else None


def load_mapping_from_kontekst_trace(trace_path: Path, value_source: str) -> tuple[dict[str, str], dict[str, Any]]:
    """Loads latest complete verify run from lesson1_kontekst trace and maps it to A..J."""

    if not trace_path.exists():
        raise FileNotFoundError(f"Trace file not found: {trace_path}")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for raw_line in trace_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        entry = json.loads(raw_line)
        parsed = _extract_verify_index_and_id(str(entry.get("step", "")))
        if not parsed:
            continue
        attempt = int(entry.get("attempt") or 0)
        grouped.setdefault(attempt, []).append(entry)

    if not grouped:
        raise ValueError("No VERIFY_ITEM entries found in trace.")

    # Choose the latest attempt with at least 10 verify calls.
    selected_attempt = None
    for attempt in sorted(grouped.keys(), reverse=True):
        if len(grouped[attempt]) >= 10:
            selected_attempt = attempt
            break
    if selected_attempt is None:
        raise ValueError("No complete attempt with 10 verify entries found.")

    selected_entries = grouped[selected_attempt]
    ordered_records: list[tuple[int, str]] = []
    labeled_records: dict[str, str] = {}
    detected_markers: list[str] = []
    detected_prompt_labels: list[str] = []

    for entry in selected_entries:
        parsed = _extract_verify_index_and_id(str(entry.get("step", "")))
        if not parsed:
            continue
        index, item_id = parsed
        value = _pick_auto_value(entry, value_source, item_id)
        ordered_records.append((index, value))
        prompt_label = _extract_prompt_label(entry)
        if prompt_label:
            labeled_records[prompt_label] = value
            detected_prompt_labels.append(prompt_label)
        detected_markers.extend(_find_letter_markers(entry))

    ordered_records.sort(key=lambda row: row[0])
    ordered_values = [value for _, value in ordered_records[:10]]

    if len(ordered_values) < 10:
        raise ValueError("Selected attempt does not provide 10 ordered values.")

    if all(label in labeled_records for label in EXPECTED_KEYS):
        mapping = {label: labeled_records[label] for label in EXPECTED_KEYS}
        mapping_mode = "prompt_labels"
    else:
        mapping = {key: value for key, value in zip(EXPECTED_KEYS, ordered_values)}
        mapping_mode = "verify_order"

    meta = {
        "trace_path": str(trace_path),
        "selected_attempt": selected_attempt,
        "value_source": value_source,
        "mapping_mode": mapping_mode,
        "ordered_values": ordered_values,
        "detected_prompt_labels": detected_prompt_labels,
        "detected_letter_markers": detected_markers,
    }
    return mapping, meta


def validate_mapping(mapping: dict[str, str]) -> None:
    """Validates that mapping contains all keys from A to J."""

    missing = [key for key in EXPECTED_KEYS if key not in mapping]
    if missing:
        raise ValueError(f"Missing keys in input mapping: {', '.join(missing)}")


def reorder_by_hint(mapping: dict[str, str]) -> list[str]:
    """Reorders values according to the side-quest hint sequence."""

    return [mapping[key] for key in HINT_ORDER]


def build_candidates(reordered: list[str]) -> dict[str, str]:
    """Builds common answer variants to speed up manual verification."""

    return {
        "joined_no_separator": "".join(reordered),
        "joined_dash": "-".join(reordered),
        "joined_space": " ".join(reordered),
        "joined_comma": ",".join(reordered),
    }


def save_result(path: Path, payload: dict[str, Any]) -> None:
    """Saves final side-quest payload to JSON output."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    """Appends one JSON object line to a JSONL trace file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def post_json(verify_url: str, payload: dict[str, Any], timeout_seconds: int) -> tuple[int, Any]:
    """Posts one JSON payload and returns (status_code, parsed_response_or_raw)."""

    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = Request(
        verify_url,
        data=raw,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            status_code = response.getcode()
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")
        status_code = error.code
    except URLError as error:
        raise RuntimeError(str(error)) from error

    try:
        body = json.loads(response_text)
    except Exception:
        body = {"raw_text": response_text}
    return status_code, body


def get_text(url: str, timeout_seconds: int) -> tuple[int, str]:
    """Performs HTTP GET request and returns status with UTF-8 text body."""

    request = Request(url, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310
            response_text = response.read().decode("utf-8", errors="replace")
            status_code = response.getcode()
    except HTTPError as error:
        response_text = error.read().decode("utf-8", errors="replace")
        status_code = error.code
    except URLError as error:
        raise RuntimeError(str(error)) from error
    return status_code, response_text


def extract_flag(payload: Any) -> str | None:
    """Extracts first {FLG:...} token from any JSON-serializable payload."""

    blob = json.dumps(payload, ensure_ascii=False)
    match = FLAG_RE.search(blob)
    return match.group(0) if match else None


def resolve_credentials(args: argparse.Namespace) -> tuple[str, str]:
    """Resolves API key and task name from args/environment with strict validation."""

    current_dir = Path(__file__).resolve().parent
    season2_dir = current_dir.parent
    root_dir = season2_dir.parent
    load_env_file(root_dir / ".env")
    load_env_file(season2_dir / ".env")
    load_env_file(current_dir / ".env")

    api_key = (args.apikey or os.getenv("HUB_API_KEY") or os.getenv("API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Missing API key. Pass --apikey or set HUB_API_KEY/API_KEY in .env.")

    task = (
        args.task
        or os.getenv("SIDEQUEST_TASK_NAME")
        or os.getenv("CATEGORIZE_TASK_NAME")
        or "categorize"
    )
    return api_key, task.strip()


def resolve_csv_url(args: argparse.Namespace, api_key: str) -> str:
    """Resolves CSV URL from args/environment with fallback built from API key."""

    return (
        (args.csv_url or "").strip()
        or os.getenv("CATEGORIZE_CSV_URL", "").strip()
        or os.getenv("ITEMS_CSV_URL", "").strip()
        or f"https://hub.ag3nts.org/data/{api_key}/categorize.csv"
    )


def load_prompt_template(args: argparse.Namespace) -> str:
    """Loads prompt template from CLI override or lesson1_kontekst output fallback."""

    if args.prompt_template:
        template = args.prompt_template.strip()
    elif args.prompt_template_file and args.prompt_template_file.exists():
        payload = json.loads(args.prompt_template_file.read_text(encoding="utf-8"))
        template = str(payload.get("template") or "").strip()
    else:
        template = ""

    if not template:
        template = DEFAULT_PROMPT_TEMPLATE

    required = ["{id}", "{description}"]
    if not all(token in template for token in required):
        raise RuntimeError("Prompt template must include placeholders: {id} and {description}.")
    return template


def build_submission_payloads(api_key: str, task: str, candidates: dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
    """Builds a list of plausible payload variants for side-quest verify submission."""

    joined = candidates["joined_no_separator"]
    dashed = candidates["joined_dash"]
    spaced = candidates["joined_space"]
    comma = candidates["joined_comma"]

    variants: list[tuple[str, dict[str, Any]]] = [
        ("answer_string_joined", {"apikey": api_key, "task": task, "answer": joined}),
        ("answer_string_dash", {"apikey": api_key, "task": task, "answer": dashed}),
        ("answer_string_space", {"apikey": api_key, "task": task, "answer": spaced}),
        ("answer_string_comma", {"apikey": api_key, "task": task, "answer": comma}),
        ("answer_obj_code", {"apikey": api_key, "task": task, "answer": {"code": joined}}),
        ("answer_obj_sequence", {"apikey": api_key, "task": task, "answer": {"sequence": joined}}),
        ("answer_obj_order", {"apikey": api_key, "task": task, "answer": {"order": dashed}}),
        ("answer_obj_text", {"apikey": api_key, "task": task, "answer": {"text": joined}}),
        ("answer_obj_prompt_raw", {"apikey": api_key, "task": task, "answer": {"prompt": joined}}),
        ("answer_obj_prompt_desc", {"apikey": api_key, "task": task, "answer": {"prompt": f"SIDEQUEST:{joined}"}}),
    ]
    return variants


def load_prompt_map_from_cycle_log(cycle_log_path: Path) -> tuple[dict[str, str], dict[str, Any]]:
    """Loads A..J prompt mapping from latest complete cycle_log attempt with responses."""

    if not cycle_log_path.exists():
        raise FileNotFoundError(f"Cycle log not found: {cycle_log_path}")

    grouped: dict[int, list[dict[str, Any]]] = {}
    for raw_line in cycle_log_path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip():
            continue
        row = json.loads(raw_line)
        if "prompt" not in row:
            continue
        attempt = int(row.get("attempt") or 0)
        grouped.setdefault(attempt, []).append(row)

    selected_attempt = None
    for attempt in sorted(grouped.keys(), reverse=True):
        rows = grouped[attempt]
        if len(rows) >= 10 and any("response" in row for row in rows):
            selected_attempt = attempt
            break
    if selected_attempt is None:
        raise ValueError("No complete cycle with prompts and responses found in cycle log.")

    rows = grouped[selected_attempt]
    rows.sort(key=lambda row: int(row.get("index") or 0))
    rows = rows[:10]

    mapping: dict[str, str] = {}
    for i, row in enumerate(rows, start=1):
        label = str(row.get("label") or ITEM_LABELS[i - 1]).strip().upper()
        mapping[label] = str(row["prompt"])

    if any(label not in mapping for label in EXPECTED_KEYS):
        raise ValueError("Prompt mapping from cycle log is incomplete for A..J.")

    meta = {
        "cycle_log_path": str(cycle_log_path),
        "selected_attempt": selected_attempt,
    }
    return mapping, meta


def parse_items_from_csv(csv_text: str) -> list[dict[str, str]]:
    """Parses first 10 items from CSV and normalizes fields to id/description."""

    reader = csv.DictReader(csv_text.splitlines())
    items: list[dict[str, str]] = []
    for row in reader:
        lowered = {str(k).strip().lower(): str(v).strip() for k, v in row.items()}
        item_id = (
            lowered.get("id")
            or lowered.get("item_id")
            or lowered.get("itemid")
            or lowered.get("uid")
            or lowered.get("code")
            or ""
        ).strip()
        description = (
            lowered.get("description")
            or lowered.get("desc")
            or lowered.get("opis")
            or lowered.get("details")
            or lowered.get("item_description")
            or ""
        ).strip()
        if not item_id:
            item_id = str(len(items) + 1)
        if not description:
            description = " | ".join(f"{k}:{v}" for k, v in row.items() if str(v).strip()) or "(empty)"
        items.append({"id": item_id, "description": description})

    if len(items) < 10:
        raise RuntimeError(f"CSV has fewer than 10 rows: {len(items)}")
    return items[:10]


def submit_replay_order(
    api_key: str,
    task: str,
    csv_url: str,
    prompt_template: str,
    verify_url: str,
    timeout_seconds: int,
    trace_path: Path,
) -> dict[str, Any]:
    """Resets balance, fetches fresh CSV, and classifies 10 prompts in hint order."""

    reset_payload = {"apikey": api_key, "task": task, "answer": {"prompt": "reset"}}
    reset_status, reset_body = post_json(verify_url, reset_payload, timeout_seconds)
    append_jsonl(
        trace_path,
        {
            "step": "reset",
            "request_body": reset_payload,
            "status_code": reset_status,
            "response_body": reset_body,
        },
    )

    csv_status, csv_text = get_text(csv_url, timeout_seconds)
    append_jsonl(
        trace_path,
        {
            "step": "fetch_csv_after_reset",
            "request_url": csv_url,
            "status_code": csv_status,
            "response_preview": csv_text[:500],
            "response_length": len(csv_text),
        },
    )
    if csv_status >= 400:
        return {
            "ok": False,
            "message": "Failed to fetch CSV after reset.",
            "status_code": csv_status,
            "response_preview": csv_text[:200],
        }

    items = parse_items_from_csv(csv_text)
    label_to_item = {label: item for label, item in zip(ITEM_LABELS, items)}

    last_response: Any = reset_body
    for index, label in enumerate(HINT_ORDER, start=1):
        item = label_to_item[label]
        prompt = prompt_template.format(
            label=label,
            id=item["id"],
            description=item["description"],
        )
        payload = {"apikey": api_key, "task": task, "answer": {"prompt": prompt}}
        status, body = post_json(verify_url, payload, timeout_seconds)
        append_jsonl(
            trace_path,
            {
                "step": f"replay_{index}_{label}",
                "request_body": payload,
                "status_code": status,
                "response_body": body,
            },
        )
        last_response = body
        flag = extract_flag(body)
        if flag:
            return {
                "ok": True,
                "flag": flag,
                "replay_step": f"replay_{index}_{label}",
                "label": label,
                "item_id": item["id"],
                "status_code": status,
                "response_body": body,
            }

        # Stop immediately on wrong classification / budget failure.
        response_code = body.get("code") if isinstance(body, dict) else None
        if status >= 400 or response_code in {-890, -910, -930, -940}:
            return {
                "ok": False,
                "message": "Replay stopped on first failed classify call.",
                "replay_step": f"replay_{index}_{label}",
                "label": label,
                "item_id": item["id"],
                "status_code": status,
                "response_body": body,
            }

    return {
        "ok": False,
        "message": "Replay completed but no flag found.",
        "used_item_ids": [label_to_item[label]["id"] for label in HINT_ORDER],
        "last_response": last_response,
    }


def submit_candidates(
    verify_url: str,
    timeout_seconds: int,
    variants: list[tuple[str, dict[str, Any]]],
    trace_path: Path,
) -> dict[str, Any]:
    """Submits candidate payloads to central and returns first successful/flagged response."""

    for index, (name, payload) in enumerate(variants, start=1):
        trace_entry: dict[str, Any] = {
            "index": index,
            "name": name,
            "url": verify_url,
            "request_body": payload,
        }
        try:
            status_code, body = post_json(verify_url, payload, timeout_seconds)

            trace_entry["status_code"] = status_code
            trace_entry["response_body"] = body
            append_jsonl(trace_path, trace_entry)

            flag = extract_flag(body)
            if flag:
                return {
                    "ok": True,
                    "flag": flag,
                    "variant": name,
                    "status_code": status_code,
                    "response_body": body,
                }
        except Exception as error:  # noqa: BLE001
            trace_entry["error"] = str(error)
            append_jsonl(trace_path, trace_entry)

    return {"ok": False, "message": "No flag found in tested submission variants."}


def main() -> None:
    """Runs the side-quest reorder flow and prints ready-to-use results."""

    args = parse_args()

    sources_used = sum(1 for source in (args.values, args.input_json, args.input_text) if source)
    trace_meta: dict[str, Any] | None = None

    if sources_used > 1:
        raise SystemExit("Use at most one explicit source: --values OR --input-json OR --input-text.")

    if args.values:
        mapping = build_mapping_from_values(list(args.values))
    elif args.input_json:
        mapping = load_mapping_from_json(args.input_json)
    elif args.input_text:
        mapping = load_mapping_from_text(args.input_text)
    else:
        mapping, trace_meta = load_mapping_from_kontekst_trace(
            trace_path=args.trace,
            value_source=args.value_source,
        )

    validate_mapping(mapping)
    reordered = reorder_by_hint(mapping)
    candidates = build_candidates(reordered)

    result = {
        "hint_order": HINT_ORDER,
        "input_keys_order": EXPECTED_KEYS,
        "source_mapping": mapping,
        "reordered_values": reordered,
        "candidates": candidates,
    }
    if trace_meta is not None:
        result["trace_meta"] = trace_meta
    save_result(args.output, result)

    print("Side quest reorder completed.")
    print(f"Hint order: {'-'.join(HINT_ORDER)}")
    print(f"Output saved: {args.output}")
    if trace_meta is not None:
        markers = trace_meta.get("detected_letter_markers") or []
        unique_markers = sorted(set(markers))
        print(f"Auto source: {trace_meta['trace_path']}")
        print(f"Selected attempt: {trace_meta['selected_attempt']}")
        print(f"Detected letter markers in responses: {unique_markers if unique_markers else 'none'}")
    print("\nCandidates:")
    for key, value in candidates.items():
        print(f"- {key}: {value}")

    if args.submit:
        api_key, task = resolve_credentials(args)
        csv_url = resolve_csv_url(args, api_key)
        prompt_template = load_prompt_template(args)
        submit_trace_path = args.output.parent / "submit_trace.jsonl"
        if args.submit_mode == "variants":
            variants = build_submission_payloads(api_key=api_key, task=task, candidates=candidates)
            submit_result = submit_candidates(
                verify_url=args.verify_url,
                timeout_seconds=args.timeout_seconds,
                variants=variants,
                trace_path=submit_trace_path,
            )
        else:
            submit_result = submit_replay_order(
                api_key=api_key,
                task=task,
                csv_url=csv_url,
                prompt_template=prompt_template,
                verify_url=args.verify_url,
                timeout_seconds=args.timeout_seconds,
                trace_path=submit_trace_path,
            )
            submit_result["prompt_template"] = prompt_template
            submit_result["csv_url"] = csv_url

        result["submit"] = submit_result
        save_result(args.output, result)

        print("\nSubmission:")
        print(f"- verify_url: {args.verify_url}")
        print(f"- task: {task}")
        print(f"- mode: {args.submit_mode}")
        print(f"- trace: {submit_trace_path}")
        if submit_result.get("ok"):
            print(f"- FLAG: {submit_result['flag']}")
            if "variant" in submit_result:
                print(f"- variant: {submit_result['variant']}")
            if "replay_step" in submit_result:
                print(f"- replay_step: {submit_result['replay_step']}")
            if "label" in submit_result:
                print(f"- label: {submit_result['label']}")
        else:
            print(f"- {submit_result['message']}")


if __name__ == "__main__":
    main()
