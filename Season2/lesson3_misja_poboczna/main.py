from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent
SEASON2_DIR = BASE_DIR.parent
PROJECT_ROOT = SEASON2_DIR.parent
DEFAULT_BASE_LOGS = SEASON2_DIR / "lesson3_failure" / "output" / "final_logs.txt"


class Settings(BaseSettings):
    """Runtime configuration for side mission probing on task `failure`."""

    model_config = SettingsConfigDict(
        env_file=(SEASON2_DIR / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hub_api_key: str | None = Field(default=None, alias="HUB_API_KEY")
    api_key: str | None = Field(default=None, alias="API_KEY")
    verify_url: str = Field(default="https://hub.ag3nts.org/verify", alias="VERIFY_URL")
    task_name: str = Field(default="failure", alias="SIDE_TASK_NAME")
    timeout_s: int = Field(default=45, alias="REQUEST_TIMEOUT_SECONDS", ge=5, le=300)

    answer_field: str = Field(default="logs", alias="SIDE_ANSWER_FIELD")
    max_attempts: int = Field(default=24, alias="SIDE_MAX_ATTEMPTS", ge=1, le=500)
    stop_on_flag: bool = Field(default=False, alias="SIDE_STOP_ON_FLAG")

    base_logs_path: str = Field(default=str(DEFAULT_BASE_LOGS), alias="SIDE_BASE_LOGS_PATH")
    output_dir_name: str = Field(default="output", alias="SIDE_OUTPUT_DIR_NAME")

    @field_validator("hub_api_key", "api_key", mode="before")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        """Normalizes optional string env values."""

        if value is None:
            return None
        norm = str(value).strip()
        return norm or None

    def resolved_hub_key(self) -> str:
        """Returns HUB key with fallback."""

        key = self.hub_api_key or self.api_key
        if not key:
            raise RuntimeError("Missing HUB_API_KEY/API_KEY in environment.")
        return key

    def output_dir(self) -> Path:
        """Returns output directory path."""

        return BASE_DIR / self.output_dir_name


class HubClient:
    """HTTP client for verify endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.key = settings.resolved_hub_key()

    def verify(self, logs: str) -> dict[str, Any]:
        """Sends one logs payload and parses JSON response."""

        payload = {
            "apikey": self.key,
            "task": self.s.task_name,
            "answer": {self.s.answer_field: logs},
        }
        response = requests.post(self.s.verify_url, json=payload, timeout=self.s.timeout_s)
        try:
            return response.json()
        except ValueError:
            return {"code": -997, "message": response.text.strip() or "<empty>", "status": response.status_code}


def stage_log(message: str) -> None:
    """Prints timestamped stage logs."""

    print(f"[stage {datetime.now().strftime('%H:%M:%S')}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Writes JSON payload to file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    """Appends one JSON line to trace file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def flatten_keys(payload: Any, prefix: str = "") -> set[str]:
    """Flattens nested JSON-like payload into dotted key paths."""

    keys: set[str] = set()
    if isinstance(payload, dict):
        for k, v in payload.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            keys.add(p)
            keys.update(flatten_keys(v, p))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            p = f"{prefix}[{idx}]"
            keys.add(p)
            keys.update(flatten_keys(item, p))
    return keys


def extract_flag_candidates(blob: str) -> list[str]:
    """Extracts explicit FLG patterns from serialized response."""

    return re.findall(r"\{FLG:[^}]+\}", blob)


def extract_side_chars(payload: dict[str, Any]) -> list[str]:
    """Extracts possible side-hint characters from response fields and message."""

    out: list[str] = []
    for key in ("token", "tokens", "noLetterSent", "wrongToken", "wrong_token", "character", "char"):
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            out.extend(list(text))

    message = str(payload.get("message", ""))
    for m in re.findall(r"['\"]([A-Za-z0-9{}_:\-])['\"]", message):
        out.append(m)
    for m in re.findall(r"(?:token|char|character)\s*[:=]\s*([A-Za-z0-9{}_:\-]+)", message, flags=re.IGNORECASE):
        out.extend(list(m))
    return out


def load_base_logs(path_str: str) -> str:
    """Loads base logs text for mutation probes."""

    path = Path(path_str)
    if not path.exists():
        raise RuntimeError(f"Base logs file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(f"Base logs file is empty: {path}")
    return text


def mutate_logs(base_text: str, max_attempts: int) -> list[tuple[str, str]]:
    """Generates deterministic malformed/partial variants for side probing."""

    lines = [x for x in base_text.splitlines() if x.strip()]
    variants: list[tuple[str, str]] = []

    def add(name: str, candidate_lines: list[str]) -> None:
        if not candidate_lines:
            return
        payload = "\n".join(candidate_lines)
        if any(payload == existing for _, existing in variants):
            return
        variants.append((name, payload))

    add("baseline", lines)
    add("drop_last_1", lines[:-1])
    add("drop_last_3", lines[:-3])
    add("drop_first_1", lines[1:])
    add("drop_first_3", lines[3:])

    non_fw = [ln for ln in lines if "FIRMWARE" not in ln]
    add("remove_firmware", non_fw)

    crit_only = [ln for ln in lines if "[CRIT]" in ln]
    add("crit_only", crit_only)

    crit_warn = [ln for ln in lines if "[CRIT]" in ln or "[WARN]" in ln]
    add("crit_warn_only", crit_warn)

    no_erro = [ln for ln in lines if "[ERRO]" not in ln and "[ERROR]" not in ln]
    add("remove_errors", no_erro)

    # Chronology breaker: swap two nearby lines.
    if len(lines) >= 8:
        swapped = list(lines)
        i = min(6, len(swapped) - 2)
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        add("swap_adjacent", swapped)

    # Truncate messages to induce quality issues while keeping format.
    compact = []
    for ln in lines:
        m = re.match(r"^(\[[^\]]+\]\s+\[[^\]]+\]\s+\S+\s+)(.+)$", ln)
        if not m:
            compact.append(ln)
            continue
        head, msg = m.group(1), m.group(2)
        short = msg[:55].rstrip(" ,;:-") + ("..." if len(msg) > 55 else "")
        compact.append(head + short)
    add("short_messages", compact)

    # Remove each core device once to force structured missing feedback.
    for device in ("FIRMWARE", "STMTURB12", "PWR01", "WTRPMP", "WSTPOOL2", "ECCS8", "WTANK07"):
        reduced = [ln for ln in lines if device not in ln]
        add(f"remove_{device}", reduced)

    return variants[:max_attempts]


def run_side_solver() -> None:
    """Runs side-mission probe strategy on failure task with full-log mutations."""

    s = Settings()
    out_dir = s.output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "submit_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()

    if s.answer_field != "logs":
        raise RuntimeError("SIDE_ANSWER_FIELD must be 'logs' for failure side probing.")

    base_logs = load_base_logs(s.base_logs_path)
    variants = mutate_logs(base_logs, s.max_attempts)
    if not variants:
        raise RuntimeError("No payload variants generated.")

    client = HubClient(s)
    stage_log(f"start task={s.task_name} variants={len(variants)}")

    recovered: list[str] = []
    seen: set[str] = set()
    flag_hits: list[str] = []
    response_dump_dir = out_dir / "responses"
    response_dump_dir.mkdir(parents=True, exist_ok=True)
    keys_success: set[str] = set()
    keys_error: set[str] = set()

    for idx, (name, payload) in enumerate(variants, start=1):
        data = client.verify(payload)
        blob = json.dumps(data, ensure_ascii=False)
        message = str(data.get("message", ""))
        write_json(response_dump_dir / f"attempt_{idx:02d}_{name}.json", data)
        flat_keys = flatten_keys(data)
        if int(data.get("code", 0)) == 0:
            keys_success.update(flat_keys)
        else:
            keys_error.update(flat_keys)

        for flg in extract_flag_candidates(blob):
            if flg not in flag_hits:
                flag_hits.append(flg)

        chars = extract_side_chars(data)
        for ch in chars:
            if ch not in seen:
                seen.add(ch)
                recovered.append(ch)

        append_jsonl(
            trace_path,
            {
                "attempt": idx,
                "variant": name,
                "line_count": len([x for x in payload.splitlines() if x.strip()]),
                "code": data.get("code"),
                "message": message[:350],
                "chars_extracted": chars,
                "recovered_so_far": "".join(recovered),
                "flag_hits": flag_hits,
            },
        )

        print(
            f"[attempt {idx}/{len(variants)}] variant={name} code={data.get('code')} "
            f"chars+={''.join(chars) if chars else '-'} recovered={''.join(recovered) or '-'}"
        )

        if s.stop_on_flag and flag_hits:
            break

    joined = "".join(recovered)
    diff_report = {
        "success_only_keys": sorted(keys_success - keys_error),
        "error_only_keys": sorted(keys_error - keys_success),
        "common_keys": sorted(keys_success & keys_error),
    }
    write_json(out_dir / "response_keys_diff.json", diff_report)
    result = {
        "task": s.task_name,
        "base_logs_path": s.base_logs_path,
        "attempts_executed": idx,
        "recovered_chars_unique_order": joined,
        "flag_candidates": list(dict.fromkeys(flag_hits + [joined, f"FLAG{{{joined}}}", f"{{FLG:{joined}}}"])) if joined else flag_hits,
        "trace_file": str(trace_path),
        "response_dump_dir": str(response_dump_dir),
        "response_keys_diff_file": str(out_dir / "response_keys_diff.json"),
    }
    write_json(out_dir / "result.json", result)
    stage_log("done")
    if flag_hits:
        print(flag_hits[0])
    else:
        print("Brak jawnej flagi. Sprawdz output/result.json i output/submit_trace.jsonl.")


def main() -> None:
    """Script entrypoint."""

    run_side_solver()


if __name__ == "__main__":
    """Runs script when executed directly."""

    main()
