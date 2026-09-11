from __future__ import annotations

import json
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
    """Runtime config for probing noLetterSent behavior on /verify."""

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
    base_logs_path: str = Field(default=str(DEFAULT_BASE_LOGS), alias="SIDE_BASE_LOGS_PATH")
    output_dir_name: str = Field(default="output", alias="SIDE_OUTPUT_DIR_NAME")

    @field_validator("hub_api_key", "api_key", mode="before")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        """Normalizes optional env values."""

        if value is None:
            return None
        val = str(value).strip()
        return val or None

    def resolved_hub_key(self) -> str:
        """Returns HUB key with fallback."""

        key = self.hub_api_key or self.api_key
        if not key:
            raise RuntimeError("Missing HUB_API_KEY/API_KEY in environment.")
        return key

    def output_dir(self) -> Path:
        """Returns output directory path."""

        return BASE_DIR / self.output_dir_name


def stage_log(message: str) -> None:
    """Prints short stage logs."""

    print(f"[stage {datetime.now().strftime('%H:%M:%S')}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Writes JSON payload to disk."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    """Appends one JSON object line."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


class HubClient:
    """HTTP client for /verify."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.key = settings.resolved_hub_key()

    def verify(self, logs_payload: str) -> dict[str, Any]:
        """Sends one attempt to verifier and parses JSON response."""

        payload = {
            "apikey": self.key,
            "task": self.s.task_name,
            "answer": {self.s.answer_field: logs_payload},
        }
        response = requests.post(self.s.verify_url, json=payload, timeout=self.s.timeout_s)
        try:
            return response.json()
        except ValueError:
            return {"code": -997, "message": response.text.strip() or "<empty>", "status": response.status_code}


def build_variants(base_logs: str) -> list[tuple[str, str]]:
    """Builds targeted malformed variants to probe noLetterSent."""

    lines = [x for x in base_logs.splitlines() if x.strip()]
    variants: list[tuple[str, str]] = []

    def add(name: str, payload: str) -> None:
        if any(payload == existing for _, existing in variants):
            return
        variants.append((name, payload))

    add("empty_payload", "")
    add("single_word", "test")
    add("json_like", '{"logs":"x"}')
    add("flg_level", "[2026-03-20 10:00] [FLG] FIRMWARE side hint test")
    add("flaga_level", "[2026-03-20 10:00] [FLAGA] FIRMWARE side hint test")
    add("missing_message", "[2026-03-20 10:00] [CRIT] FIRMWARE")
    add("bad_date", "[20-03-2026 10:00] [CRIT] FIRMWARE malformed date")
    add("bad_time", "[2026-03-20 99:99] [CRIT] FIRMWARE malformed time")
    add("wrong_sep", "[2026/03/20 10:00] [CRIT] FIRMWARE wrong separator")
    add("chrono_reverse", "\n".join(reversed(lines[-20:])))
    add("remove_all_firmware", "\n".join([ln for ln in lines if "FIRMWARE" not in ln]))
    add("crit_only", "\n".join([ln for ln in lines if "[CRIT]" in ln]))
    add("warn_only", "\n".join([ln for ln in lines if "[WARN]" in ln]))
    add("erro_only", "\n".join([ln for ln in lines if "[ERRO]" in ln or "[ERROR]" in ln]))
    add("dup_noise", "\n".join(lines[:1] * 40))
    add("valid_baseline", "\n".join(lines))
    return variants


def run_probe() -> None:
    """Runs noLetterSent probing campaign and stores full responses."""

    s = Settings()
    if s.answer_field != "logs":
        raise RuntimeError("For failure probing SIDE_ANSWER_FIELD must be 'logs'.")
    base_path = Path(s.base_logs_path)
    if not base_path.exists():
        raise RuntimeError(f"Base logs file not found: {base_path}")
    base_logs = base_path.read_text(encoding="utf-8")
    if not base_logs.strip():
        raise RuntimeError(f"Base logs file is empty: {base_path}")

    out_dir = s.output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "probe_nolettersent_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    dump_dir = out_dir / "probe_nolettersent_responses"
    dump_dir.mkdir(parents=True, exist_ok=True)

    variants = build_variants(base_logs)
    client = HubClient(s)
    stage_log(f"start noLetterSent probe variants={len(variants)}")

    unique_no_letter: set[str] = set()
    summary_rows: list[dict[str, Any]] = []

    for idx, (name, payload) in enumerate(variants, start=1):
        data = client.verify(payload)
        no_letter = data.get("noLetterSent")
        if no_letter is not None:
            unique_no_letter.add(str(no_letter))

        row = {
            "attempt": idx,
            "variant": name,
            "payload_lines": len([x for x in payload.splitlines() if x.strip()]),
            "code": data.get("code"),
            "message": str(data.get("message", ""))[:300],
            "tokenCount": data.get("tokenCount"),
            "lineCount": data.get("lineCount"),
            "noLetterSent": data.get("noLetterSent"),
        }
        summary_rows.append(row)
        append_jsonl(trace_path, row)
        write_json(dump_dir / f"attempt_{idx:02d}_{name}.json", data)

        print(
            f"[attempt {idx}/{len(variants)}] variant={name} code={data.get('code')} "
            f"noLetterSent={data.get('noLetterSent')!r}"
        )

    result = {
        "task": s.task_name,
        "variants_tested": len(variants),
        "unique_noLetterSent_values": sorted(unique_no_letter),
        "trace_file": str(trace_path),
        "response_dump_dir": str(dump_dir),
        "summary": summary_rows,
    }
    write_json(out_dir / "probe_nolettersent_result.json", result)
    stage_log("done")
    print("Wynik: output/probe_nolettersent_result.json")


def main() -> None:
    """Script entrypoint."""

    run_probe()


if __name__ == "__main__":
    """Runs script when executed directly."""

    main()
