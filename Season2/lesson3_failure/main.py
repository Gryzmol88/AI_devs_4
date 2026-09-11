from __future__ import annotations

import json
import math
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "failure"
BASE_DIR = Path(__file__).resolve().parent
SEASON2_DIR = BASE_DIR.parent
PROJECT_ROOT = SEASON2_DIR.parent
BASE_COMPONENTS = ("ECCS8", "WTANK07", "WTRPMP", "WSTPOOL2", "PWR01", "STMTURB12", "FIRMWARE")
BLOCKED_TOKENS = {"CRIT", "ERRO", "ERROR", "WARN", "INFO", "DEBUG", "TRACE", "TOKEN", "USAGE"}
FIRMWARE_PATTERNS = (
    ("validation queue",),
    ("watchdog",),
    ("cross-check", "compatibility verification"),
    ("manual override", "safe shutdown state"),
)
CAUSAL_KEYWORDS = (
    "failed",
    "cannot",
    "can't",
    "trip",
    "interlock",
    "critical stop",
    "shutdown",
    "below",
    "degraded",
    "fault",
    "runaway",
    "lost stable",
    "compromised",
    "saturated",
)

SEVERITY_STAGES: tuple[tuple[str, ...], ...] = (
    ("CRIT",),
    ("CRIT", "WARN"),
    ("CRIT", "WARN", "ERRO", "ERROR"),
)


class Settings(BaseSettings):
    """Runtime configuration loaded from `Season2/.env` and root `.env`."""

    model_config = SettingsConfigDict(
        env_file=(SEASON2_DIR / ".env", PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )
    hub_api_key: str | None = Field(default=None, alias="HUB_API_KEY")
    api_key: str | None = Field(default=None, alias="API_KEY")
    verify_url: str = Field(default=VERIFY_URL, alias="VERIFY_URL")
    task_name: str = Field(default=TASK_NAME, alias="FAILURE_TASK_NAME")
    log_url_template: str = Field(default="https://hub.ag3nts.org/data/{apikey}/failure.log", alias="FAILURE_LOG_URL_TEMPLATE")
    timeout_s: int = Field(default=60, alias="REQUEST_TIMEOUT_SECONDS", ge=5, le=300)
    max_attempts: int = Field(default=8, alias="FAILURE_MAX_ATTEMPTS", ge=1, le=60)
    target_tokens: int = Field(default=1305, alias="FAILURE_TARGET_TOKENS", ge=300, le=1499)
    hard_limit: int = Field(default=1500, alias="FAILURE_HARD_TOKEN_LIMIT", ge=500, le=5000)
    token_char_ratio: float = Field(default=3.6, alias="FAILURE_TOKEN_CHAR_RATIO", ge=2.5, le=6.0)
    output_dir_name: str = Field(default="output", alias="FAILURE_OUTPUT_DIR_NAME")

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openrouter_base_url: str = Field(default="https://openrouter.ai/api/v1", alias="OPENROUTER_BASE_URL")
    llm_model: str = Field(default="gpt-5-mini", alias="FAILURE_AGENT_MODEL")
    agent_max_steps: int = Field(default=60, alias="FAILURE_AGENT_MAX_STEPS", ge=10, le=400)
    llm_log_compression: bool = Field(default=True, alias="FAILURE_LLM_LOG_COMPRESSION")
    llm_compression_batch_size: int = Field(default=24, alias="FAILURE_LLM_COMPRESSION_BATCH_SIZE", ge=4, le=80)
    llm_compression_target_chars: int = Field(default=96, alias="FAILURE_LLM_COMPRESSION_TARGET_CHARS", ge=40, le=220)
    llm_compression_trigger_ratio: float = Field(default=0.94, alias="FAILURE_LLM_COMPRESSION_TRIGGER_RATIO", ge=0.5, le=1.2)
    crit_context_window_minutes: int = Field(default=45, alias="FAILURE_CRIT_CONTEXT_WINDOW_MINUTES", ge=5, le=240)
    crit_context_per_device_per_anchor: int = Field(default=2, alias="FAILURE_CRIT_CONTEXT_PER_DEVICE_PER_ANCHOR", ge=1, le=6)
    llm_rank_device_logs: bool = Field(default=True, alias="FAILURE_LLM_RANK_DEVICE_LOGS")
    llm_rank_device_max_items: int = Field(default=120, alias="FAILURE_LLM_RANK_DEVICE_MAX_ITEMS", ge=20, le=300)

    @field_validator("hub_api_key", "api_key", "openai_api_key", "openrouter_api_key", mode="before")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        """Trims optional key values."""

        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None

    def resolved_hub_key(self) -> str:
        """Returns HUB key with fallback to generic API key."""

        key = self.hub_api_key or self.api_key
        if not key:
            raise RuntimeError("Missing HUB_API_KEY/API_KEY in environment.")
        return key

    def resolved_llm_key(self) -> str:
        """Returns LLM key preferring OpenAI key, then OpenRouter key."""

        key = self.openai_api_key or self.openrouter_api_key
        if not key:
            raise RuntimeError("Missing OPENAI_API_KEY/OPENROUTER_API_KEY in environment.")
        return key

    def resolved_llm_base_url(self) -> str:
        """Returns provider base URL for chat completions."""

        if self.openai_api_key:
            return self.openai_base_url.rstrip("/")
        return self.openrouter_base_url.rstrip("/")

    def llm_provider(self) -> str:
        """Returns active LLM provider name."""

        return "openai" if self.openai_api_key else "openrouter"

    def output_dir(self) -> Path:
        """Returns output directory path."""

        return BASE_DIR / self.output_dir_name


class LogEntry(BaseModel):
    """One parsed log entry."""

    timestamp: datetime
    level: str
    component: str
    message: str
    raw_line: str

    def uid(self) -> str:
        """Returns deterministic id used for dedupe."""

        return f"{self.timestamp:%Y-%m-%d %H:%M}|{self.level}|{self.component}|{self.message.lower()}"

    def render(self, chars: int) -> str:
        """Renders compact line preserving timestamp, level and component."""

        msg = re.sub(r"\s+", " ", self.message).strip()
        if len(msg) > chars:
            msg = msg[:chars].rstrip(" ,;:-") + "..."
        return f"[{self.timestamp:%Y-%m-%d %H:%M}] [{self.level}] {self.component} {msg}"


def render_entry(entry: LogEntry, chars: int, compressed_by_uid: dict[str, str] | None = None) -> str:
    """Renders one entry using optional LLM-compressed message text."""

    if compressed_by_uid and entry.uid() in compressed_by_uid:
        msg = re.sub(r"\s+", " ", compressed_by_uid[entry.uid()]).strip()
        if len(msg) > chars:
            msg = msg[:chars].rstrip(" ,;:-") + "..."
        return f"[{entry.timestamp:%Y-%m-%d %H:%M}] [{entry.level}] {entry.component} {msg}"
    return entry.render(chars)


def parse_log(raw: str) -> list[LogEntry]:
    """Parses failure.log into structured entries."""

    out: list[LogEntry] = []
    p = re.compile(r"^\[(?P<ts>[^\]]+)\]\s+\[(?P<lvl>[^\]]+)\]\s+(?P<cmp>[A-Za-z0-9_\-]+)\s+(?P<msg>.+)$")
    for line in raw.splitlines():
        m = p.match(line.strip())
        if not m:
            continue
        ts_raw = m.group("ts")
        ts = datetime.strptime(ts_raw, "%Y-%m-%d %H:%M:%S") if len(ts_raw) > 16 else datetime.strptime(ts_raw, "%Y-%m-%d %H:%M")
        out.append(LogEntry(timestamp=ts, level=m.group("lvl").upper(), component=m.group("cmp").upper(), message=m.group("msg"), raw_line=line.strip()))
    return out


def uniq(entries: list[LogEntry]) -> list[LogEntry]:
    """Deduplicates entries preserving order."""

    seen: set[str] = set()
    out: list[LogEntry] = []
    for e in entries:
        k = e.uid()
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return out


def dedupe_noise(
    entries: list[LogEntry],
    required_devices: set[str],
    preserve_ids: set[str] | None = None,
) -> list[LogEntry]:
    """Deduplicates by level+message while preserving core lines and required-device chronology."""

    preserve_ids = preserve_ids or set()
    groups: dict[tuple[str, str], list[LogEntry]] = {}
    for e in entries:
        msg = re.sub(r"\s+", " ", e.message).strip().lower()
        key = (e.level, msg)
        groups.setdefault(key, []).append(e)

    kept: list[LogEntry] = []
    for key in groups:
        group = sorted(groups[key], key=lambda x: x.timestamp)
        if len(group) == 1:
            kept.extend(group)
            continue

        preserved = [e for e in group if e.uid() in preserve_ids]
        if preserved:
            # Always keep protected core lines, plus one edge on each side to preserve timeline.
            kept.append(group[0])
            kept.extend(preserved)
            kept.append(group[-1])
            continue

        req_related = any(any(related(e, d) for d in required_devices) for e in group)
        if not required_devices and any(related(e, "FIRMWARE") for e in group):
            req_related = True
        if req_related:
            # Keep first+last event for required devices.
            kept.append(group[0])
            kept.append(group[-1])
        else:
            # For non-required noise keep newest only.
            kept.append(group[-1])

    return uniq(sorted(kept, key=lambda x: x.timestamp))


def related(e: LogEntry, component: str) -> bool:
    """Checks whether entry belongs to component directly or by mention."""

    c = component.upper()
    return e.component == c or c.lower() in e.message.lower()


def extract_missing(payload: dict[str, Any]) -> set[str]:
    """Extracts missing component names from hub feedback."""

    msg = str(payload.get("message", ""))
    names = {x.upper() for x in re.findall(r"\b([A-Z]{3,}[0-9]{0,3})\b", msg)}
    return {x for x in names if x not in BLOCKED_TOKENS}


def extract_side_chars(payload: dict[str, Any]) -> list[str]:
    """Extracts potential side-mission characters from failure feedback payload."""

    out: list[str] = []
    # Explicit fields sometimes used by verifier for side hints.
    for key in ("noLetterSent", "token", "tokens", "character", "char", "wrongToken", "wrong_token"):
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        out.extend(list(text))

    message = str(payload.get("message", ""))
    # Quoted single char markers.
    for m in re.findall(r"['\"]([A-Za-z0-9{}_:\-])['\"]", message):
        out.append(m)
    # token=<...> patterns.
    for m in re.findall(r"(?:token|char|character)\s*[:=]\s*([A-Za-z0-9{}_:\-]+)", message, flags=re.IGNORECASE):
        out.extend(list(m))
    return out


def token_est(text: str, ratio: float, mult: float = 1.0) -> int:
    """Estimates token count from text length."""

    return int(math.ceil((len(text) / ratio) * mult)) if text else 0


def write_json(path: Path, payload: Any) -> None:
    """Writes JSON file with UTF-8 encoding."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def stage_log(message: str) -> None:
    """Prints short timestamped progress log for long-running stages."""

    print(f"[stage {datetime.now().strftime('%H:%M:%S')}] {message}")


def component_packet(
    all_entries: list[LogEntry],
    component: str,
    required: bool,
    allowed_levels: set[str],
    explicit_limit: int | None = None,
) -> list[LogEntry]:
    """Builds compact packet for one component."""

    rel_all = uniq(sorted([e for e in all_entries if related(e, component)], key=lambda x: x.timestamp))
    rel = [e for e in rel_all if e.level in allowed_levels]
    if not rel and not (component == "FIRMWARE" and required):
        return []
    out: list[LogEntry] = []
    for level in ("WARN", "ERRO", "ERROR", "CRIT"):
        if level not in allowed_levels:
            continue
        first = next((e for e in rel if e.level == level), None)
        last = next((e for e in reversed(rel) if e.level == level), None)
        if first:
            out.append(first)
        if last and (not first or last.uid() != first.uid()):
            out.append(last)
    if component == "FIRMWARE":
        for patterns in FIRMWARE_PATTERNS:
            hit = next((e for e in rel if any(p in e.message.lower() for p in patterns)), None)
            if hit:
                out.append(hit)
        if required:
            # FIRMWARE requires a small INFO baseline and transition context,
            # otherwise technicians often report insufficient reconstruction.
            info_rel = [e for e in rel_all if e.level == "INFO"]
            out.extend(info_rel[:2])
            out.extend(info_rel[-2:])
            transition = next(
                (
                    e for e in rel_all
                    if any(t in e.message.lower() for t in ("constrained mode", "manual override", "safe shutdown", "guard branch"))
                ),
                None,
            )
            if transition:
                out.append(transition)
    if explicit_limit is not None:
        limit = max(1, explicit_limit)
    elif required:
        limit = 10 if component == "FIRMWARE" else 8
    else:
        limit = 5
    out.extend(rel[-limit:])
    timeline = uniq(sorted(out, key=lambda x: x.timestamp))
    if len(timeline) <= limit:
        return timeline

    # Keep compact chronology with stronger bias for end-of-day failure context.
    head_keep = 2 if required else 1
    tail_keep = max(1, limit - head_keep)
    compact = uniq(timeline[:head_keep] + timeline[-tail_keep:])
    if len(compact) > limit:
        compact = compact[-limit:]
    return uniq(sorted(compact, key=lambda x: x.timestamp))


def device_core_packet(all_entries: list[LogEntry], component: str, allowed_levels: set[str]) -> list[LogEntry]:
    """Builds strict minimal core timeline for one required component."""

    rel = uniq(sorted([e for e in all_entries if related(e, component)], key=lambda x: x.timestamp))
    rel = [e for e in rel if e.level in allowed_levels]
    if not rel:
        return []
    out: list[LogEntry] = []

    def add(e: LogEntry | None) -> None:
        if e is None:
            return
        if any(x.uid() == e.uid() for x in out):
            return
        out.append(e)

    for level in ("WARN", "ERRO", "ERROR", "CRIT"):
        if level not in allowed_levels:
            continue
        add(next((e for e in rel if e.level == level), None))
    add(next((e for e in reversed(rel) if e.level in {"ERRO", "ERROR", "CRIT"} and e.level in allowed_levels), None))
    add(next((e for e in rel if any(t in e.message.lower() for t in ("fault", "failed", "did not", "below", "trip"))), None))
    add(next((e for e in reversed(rel) if any(t in e.message.lower() for t in ("shutdown", "halted", "locked", "safe"))), None))
    if component == "FIRMWARE":
        for patterns in FIRMWARE_PATTERNS:
            add(next((e for e in rel if any(p in e.message.lower() for p in patterns)), None))
            add(next((e for e in reversed(rel) if any(p in e.message.lower() for p in patterns)), None))
    return uniq(sorted(out, key=lambda x: x.timestamp))


def firmware_enrichment_packet(all_entries: list[LogEntry]) -> list[LogEntry]:
    """Builds additional firmware context lines independent from current global severity stage."""

    rel = uniq(sorted([e for e in all_entries if related(e, "FIRMWARE")], key=lambda x: x.timestamp))
    if not rel:
        return []
    out: list[LogEntry] = []

    def add(e: LogEntry | None) -> None:
        if e is None:
            return
        if any(x.uid() == e.uid() for x in out):
            return
        out.append(e)

    add(next((e for e in rel if e.level == "WARN"), None))
    add(next((e for e in rel if e.level in {"ERRO", "ERROR"}), None))
    add(next((e for e in rel if e.level == "CRIT"), None))
    add(next((e for e in reversed(rel) if e.level in {"ERRO", "ERROR", "CRIT"}), None))

    for patterns in FIRMWARE_PATTERNS:
        add(next((e for e in rel if any(p in e.message.lower() for p in patterns)), None))
        add(next((e for e in reversed(rel) if any(p in e.message.lower() for p in patterns)), None))

    return uniq(sorted(out, key=lambda x: x.timestamp))


def firmware_core_packet(all_entries: list[LogEntry]) -> list[LogEntry]:
    """Builds non-removable compact core for FIRMWARE using exact-component events."""

    rel = uniq(sorted([e for e in all_entries if e.component == "FIRMWARE"], key=lambda x: x.timestamp))
    if not rel:
        return []
    out: list[LogEntry] = []

    def add(e: LogEntry | None) -> None:
        if e is None:
            return
        if any(x.uid() == e.uid() for x in out):
            return
        out.append(e)

    add(next((e for e in rel if e.level == "ERRO"), None))
    add(next((e for e in rel if e.level == "WARN"), None))
    add(next((e for e in rel if e.level == "CRIT"), None))
    add(next((e for e in reversed(rel) if e.level == "CRIT"), None))
    add(next((e for e in rel if "manual override" in e.message.lower()), None))
    add(next((e for e in rel if "guard branch" in e.message.lower()), None))
    add(next((e for e in reversed(rel) if "validation queue" in e.message.lower()), None))
    add(next((e for e in reversed(rel) if "watchdog" in e.message.lower()), None))
    add(next((e for e in rel if e.level == "INFO"), None))
    add(next((e for e in reversed(rel) if e.level == "INFO"), None))

    return uniq(sorted(out, key=lambda x: x.timestamp))[:10]


def crit_anchors(all_entries: list[LogEntry], required_devices: set[str], broaden_context: bool) -> list[LogEntry]:
    """Selects CRIT anchor events as the primary timeline backbone."""

    crits = [e for e in all_entries if e.level == "CRIT" and any(token in e.component for token in BASE_COMPONENTS)]
    crits = uniq(sorted(crits, key=lambda x: x.timestamp))
    if not required_devices or broaden_context:
        return crits
    return [e for e in crits if any(related(e, d) for d in required_devices)]


def nearby_context_for_required(
    all_entries: list[LogEntry],
    anchors: list[LogEntry],
    required_devices: set[str],
    allowed_levels: set[str],
    crit_only_devices: set[str],
    window_minutes: int,
    per_device_per_anchor: int,
) -> list[LogEntry]:
    """Selects events close in time to CRIT anchors for currently required devices."""

    if not anchors or not required_devices:
        return []
    # Keep this context narrow and diagnostic.
    allowed_ctx_levels = set(allowed_levels) | {"WARN", "ERRO", "ERROR"}
    out: list[LogEntry] = []
    for anchor in anchors:
        start = anchor.timestamp - timedelta(minutes=window_minutes)
        end = anchor.timestamp + timedelta(minutes=window_minutes)
        for device in sorted(required_devices):
            if device in crit_only_devices:
                device_levels = {"CRIT"}
            else:
                device_levels = set(allowed_ctx_levels)
            candidates = [
                e
                for e in all_entries
                if start <= e.timestamp <= end
                and related(e, device)
                and (e.level in device_levels or (device == "FIRMWARE" and device not in crit_only_devices and e.level == "INFO"))
            ]
            candidates = uniq(sorted(candidates, key=lambda x: x.timestamp))
            if not candidates:
                continue
            head = candidates[: max(1, per_device_per_anchor // 2)]
            tail = candidates[-(per_device_per_anchor - len(head)) :] if per_device_per_anchor > len(head) else []
            out.extend(uniq(head + tail))
    return uniq(sorted(out, key=lambda x: x.timestamp))


def message_template(message: str) -> str:
    """Builds coarse message template for near-duplicate clustering."""

    msg = re.sub(r"\s+", " ", message).strip().lower()
    msg = re.sub(r"\b\d+(\.\d+)?\b", "#", msg)
    msg = re.sub(r"\b(?:[a-z]{1,4}\d{1,3}|[a-z]{2,}\d{1,2})\b", "DEV", msg)
    return msg


def state_transition_reduce(entries: list[LogEntry], required_devices: set[str], keep_core_ids: set[str]) -> list[LogEntry]:
    """Compresses repeated states while preserving transition points and core entries."""

    grouped: dict[str, list[LogEntry]] = {}
    for e in sorted(entries, key=lambda x: x.timestamp):
        grouped.setdefault(e.component, []).append(e)

    out: list[LogEntry] = []
    for component in grouped:
        seq = grouped[component]
        prev_sig: tuple[str, str] | None = None
        for idx, e in enumerate(seq):
            sig = (e.level, message_template(e.message))
            must_keep = (
                e.uid() in keep_core_ids
                or idx == 0
                or idx == len(seq) - 1
                or component in required_devices
                and e.level in {"CRIT", "ERRO", "ERROR", "WARN"}
            )
            if must_keep or sig != prev_sig:
                out.append(e)
            prev_sig = sig
    return uniq(sorted(out, key=lambda x: x.timestamp))


def anomaly_score(entry: LogEntry, required_devices: set[str], anchors: list[LogEntry]) -> int:
    """Scores entry importance for pre-selection under tight budgets."""

    score = 0
    if entry.level == "CRIT":
        score += 100
    elif entry.level in {"ERRO", "ERROR"}:
        score += 70
    elif entry.level == "WARN":
        score += 40
    else:
        score += 15
    if any(related(entry, d) for d in required_devices):
        score += 30
    text = entry.message.lower()
    if any(k in text for k in CAUSAL_KEYWORDS):
        score += 35
    if anchors:
        delta = min(abs((entry.timestamp - a.timestamp).total_seconds()) for a in anchors)
        if delta <= 15 * 60:
            score += 20
        elif delta <= 45 * 60:
            score += 10
    return score


def score_select(entries: list[LogEntry], required_devices: set[str], anchors: list[LogEntry], max_count: int = 240) -> list[LogEntry]:
    """Keeps top scored entries with chronology preserved."""

    if len(entries) <= max_count:
        return uniq(sorted(entries, key=lambda x: x.timestamp))
    ranked = sorted(entries, key=lambda e: (-anomaly_score(e, required_devices, anchors), e.timestamp))
    picked = ranked[:max_count]
    return uniq(sorted(picked, key=lambda x: x.timestamp))


def causal_chain_entries(
    all_entries: list[LogEntry],
    required_devices: set[str],
    allowed_levels: set[str],
    crit_only_devices: set[str],
) -> list[LogEntry]:
    """Selects entries that explicitly describe failure causality."""

    out: list[LogEntry] = []
    for e in all_entries:
        if e.level not in allowed_levels and e.level not in {"ERRO", "ERROR", "WARN"}:
            continue
        if required_devices and not any(related(e, d) for d in required_devices):
            continue
        if any(related(e, d) for d in crit_only_devices) and e.level != "CRIT":
            continue
        msg = e.message.lower()
        if any(k in msg for k in CAUSAL_KEYWORDS):
            out.append(e)
    return uniq(sorted(out, key=lambda x: x.timestamp))


def build_candidate_entries(
    all_entries: list[LogEntry],
    required_devices: set[str],
    frozen_core_ids: set[str],
    broaden_context: bool,
    allowed_levels: set[str],
    crit_only_devices: set[str],
    component_limits: dict[str, int] | None = None,
    crit_context_window_minutes: int = 45,
    crit_context_per_device_per_anchor: int = 2,
) -> list[LogEntry]:
    """Builds candidate entries from base + required components + frozen core."""

    # CRIT-first strategy:
    # 1) build timeline from CRIT anchors,
    # 2) enrich with events time-close to CRIT for required devices,
    # 3) add compact component packets.
    anchors = crit_anchors(all_entries, required_devices, broaden_context)
    comps = list(BASE_COMPONENTS) if (not required_devices or broaden_context) else sorted(required_devices)
    out: list[LogEntry] = []
    by_id = {e.uid(): e for e in all_entries}
    out.extend(anchors)
    out.extend(
        nearby_context_for_required(
            all_entries,
            anchors,
            required_devices,
            allowed_levels,
            crit_only_devices,
            window_minutes=crit_context_window_minutes,
            per_device_per_anchor=crit_context_per_device_per_anchor,
        )
    )
    out.extend(causal_chain_entries(all_entries, required_devices, allowed_levels, crit_only_devices))
    for c in comps:
        limit = None if component_limits is None else component_limits.get(c)
        component_levels = {"CRIT"} if c in crit_only_devices else allowed_levels
        out.extend(component_packet(all_entries, c, c in required_devices, component_levels, explicit_limit=limit))
    if required_devices or broaden_context:
        global_crit = [
            e
            for e in all_entries
            if e.level in allowed_levels and e.level == "CRIT"
            and any(token in e.message.lower() for token in ("trip", "shutdown", "critical stop", "interlock"))
        ]
        out.extend(sorted(global_crit, key=lambda x: x.timestamp)[-8:])
        if broaden_context:
            global_warn_erro = [
                e
                for e in all_entries
                if e.level in {"WARN", "ERRO", "ERROR"} and e.level in allowed_levels
                and any(token in e.component for token in BASE_COMPONENTS)
            ]
            out.extend(sorted(global_warn_erro, key=lambda x: x.timestamp)[-16:])
    for uid in frozen_core_ids:
        if uid in by_id:
            out.append(by_id[uid])
    out = uniq(sorted(out, key=lambda x: x.timestamp))
    out = state_transition_reduce(out, required_devices, frozen_core_ids)
    out = dedupe_noise(out, required_devices, frozen_core_ids)
    out = score_select(out, required_devices, anchors)
    return uniq(sorted(out, key=lambda x: x.timestamp))


def has_required_coverage(entries: list[LogEntry], required_devices: set[str]) -> bool:
    """Checks whether each required device still appears in candidate entries."""

    for device in required_devices:
        if not any(related(e, device) for e in entries):
            return False
    return True


def render_and_fit(
    entries: list[LogEntry],
    required_devices: set[str],
    core_ids: set[str],
    target: int,
    hard: int,
    ratio: float,
    mult: float,
    compressed_by_uid: dict[str, str] | None = None,
) -> tuple[str, int]:
    """Renders and trims candidate to fit token constraints."""

    work = list(entries)
    for chars in (140, 120, 100, 85, 70, 60, 50):
        text = "\n".join(
            render_entry(
                e,
                300 if (e.component == "FIRMWARE" or related(e, "FIRMWARE"))
                else (125 if any(related(e, d) for d in required_devices) else chars)
                ,
                compressed_by_uid,
            )
            for e in work
        )
        toks = token_est(text, ratio, mult)
        if toks <= target and toks <= hard:
            return text, toks

    while work:
        removable = [e for e in work if e.uid() not in core_ids]
        if not removable:
            break

        def removal_priority(e: LogEntry) -> tuple[int, datetime]:
            req = any(related(e, d) for d in required_devices)
            if not req:
                return (
                    0 if e.level == "INFO" else
                    1 if e.level == "WARN" else
                    2 if e.level == "ERRO" else
                    3,
                    e.timestamp,
                )
            return (
                4 if e.level == "INFO" else
                5 if e.level == "WARN" else
                6 if e.level == "ERRO" else
                7,
                e.timestamp,
            )

        removed = False
        for worst in sorted(removable, key=removal_priority):
            trial = [e for e in work if e.uid() != worst.uid()]
            if not has_required_coverage(trial, required_devices):
                continue
            work = trial
            removed = True
            break
        if not removed:
            break
        text = "\n".join(render_entry(e, 100, compressed_by_uid) for e in work)
        toks = token_est(text, ratio, mult)
        if toks <= target and toks <= hard:
            return text, toks
    text = "\n".join(render_entry(e, 100, compressed_by_uid) for e in work)
    return text, token_est(text, ratio, mult)


class HubClient:
    """HTTP client for log download and verify endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.key = settings.resolved_hub_key()

    def download_log(self) -> str:
        """Downloads failure.log content."""

        url = self.s.log_url_template.format(apikey=self.key)
        response = requests.get(url, timeout=self.s.timeout_s)
        response.raise_for_status()
        return response.text

    def verify(self, logs: str) -> dict[str, Any]:
        """Sends logs to verify endpoint and parses JSON response."""

        payload = {"apikey": self.key, "task": self.s.task_name, "answer": {"logs": logs}}
        response = requests.post(self.s.verify_url, json=payload, timeout=self.s.timeout_s)
        try:
            return response.json()
        except ValueError:
            return {"code": -997, "message": response.text.strip() or "<empty>"}


class SearchSubagent:
    """Retrieval subagent that searches large logs so main agent does not ingest full dataset."""

    def __init__(self, entries: list[LogEntry]) -> None:
        self.entries = entries

    def search(self, component: str = "", keyword: str = "", level: str = "", limit: int = 20) -> list[LogEntry]:
        """Returns filtered log entries by component/keyword/level with deterministic truncation."""

        c = component.strip().upper()
        k = keyword.strip().lower()
        lv = level.strip().upper()
        hits = list(self.entries)
        if c:
            hits = [e for e in hits if related(e, c)]
        if k:
            hits = [e for e in hits if k in e.message.lower() or k in e.raw_line.lower()]
        if lv:
            hits = [e for e in hits if e.level == lv]
        hits = uniq(sorted(hits, key=lambda x: x.timestamp))
        if len(hits) > limit:
            head = hits[: limit // 2]
            tail = hits[-(limit - len(head)) :]
            hits = uniq(head + tail)
        return hits


class ChatClient:
    """OpenAI-compatible chat/completions client used for function-calling agent loop."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.api_key = settings.resolved_llm_key()
        self.base_url = settings.resolved_llm_base_url()

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Executes one chat completion call with tools."""

        payload = {"model": self.s.llm_model, "messages": messages, "tools": tools, "tool_choice": "auto"}
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.s.timeout_s,
        )
        response.raise_for_status()
        return response.json()

    def compress_batch(self, batch: list[dict[str, str]], target_chars: int) -> dict[str, str]:
        """Compresses log messages and returns mapping `id -> compressed_message`."""

        if not batch:
            return {}
        system = (
            "You compress technical incident log messages. "
            "Keep meaning, cause/effect, and key failure terms. "
            "Return ONLY valid JSON: {\"items\":[{\"id\":\"...\",\"message\":\"...\"}]}."
        )
        user = {
            "target_chars": target_chars,
            "rules": [
                "Do not invent facts.",
                "Keep language concise.",
                "Preserve words that indicate failure state.",
                "Each message should be <= target_chars when possible.",
            ],
            "items": batch,
        }
        payload = {
            "model": self.s.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.s.timeout_s,
        )
        response.raise_for_status()
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
        raw = str(content).strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return {}
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                return {}
        items = parsed.get("items", []) if isinstance(parsed, dict) else []
        out: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            k = str(item.get("id", "")).strip()
            msg = str(item.get("message", "")).strip()
            if k and msg:
                out[k] = msg
        return out

    def rank_device_logs(self, device: str, items: list[dict[str, str]]) -> list[str]:
        """Ranks device log ids by relevance to failure analysis, highest priority first."""

        if not items:
            return []
        system = (
            "You prioritize incident logs for failure analysis.\n"
            "Severity order: CRIT > ERRO/ERROR > WARN > INFO.\n"
            "Prefer entries with cause/effect and shutdown/trip context.\n"
            "Return ONLY JSON: {\"ordered_ids\":[\"id1\",\"id2\",...]}."
        )
        user = {
            "device": device,
            "rules": [
                "Prioritize logs most useful to explain what happened to this device.",
                "Demote repetitive informational logs.",
                "Keep chronology useful for incident reconstruction.",
            ],
            "items": items,
        }
        payload = {
            "model": self.s.llm_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": 0,
        }
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=self.s.timeout_s,
        )
        response.raise_for_status()
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        content = message.get("content", "")
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in content)
        raw = str(content).strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"\{[\s\S]*\}", raw)
            if not m:
                return []
            try:
                parsed = json.loads(m.group(0))
            except json.JSONDecodeError:
                return []
        ordered = parsed.get("ordered_ids", []) if isinstance(parsed, dict) else []
        return [str(x) for x in ordered if str(x).strip()]


class Toolbox:
    """Function-calling tools execution state."""

    def __init__(self, settings: Settings, hub: HubClient, entries: list[LogEntry], out_dir: Path) -> None:
        self.s = settings
        self.hub = hub
        self.entries = entries
        self.search_subagent = SearchSubagent(entries)
        self.compressor = ChatClient(settings)
        self.out_dir = out_dir
        self.required: set[str] = set()
        self.frozen_core_ids: set[str] = set()
        self.multiplier = 1.0
        self.attempt = 0
        self.last_text = ""
        self.last_tokens = 0
        self.last_selected_entries = 0
        self.last_response: dict[str, Any] | None = None
        self.flag: str | None = None
        self.force_broader_context = False
        self.severity_stage = 0
        self.missing_repeats: dict[str, int] = {}
        self.device_limits: dict[str, int] = {"FIRMWARE": 14}
        self.device_min_limits: dict[str, int] = {"FIRMWARE": 6}
        self.device_max_limits: dict[str, int] = {"FIRMWARE": 24}
        self.device_non_missing_streak: dict[str, int] = {}
        self.device_locked_min: dict[str, bool] = {}
        self.device_last_adjustment: dict[str, str] = {}
        self.device_first_seen_attempt: dict[str, int] = {}
        self.by_uid: dict[str, LogEntry] = {e.uid(): e for e in entries}
        self.device_ranked_uids: dict[str, list[str]] = self.build_device_rankings()
        self.side_chars: list[str] = []
        self.side_seen_chars: set[str] = set()
        for component in BASE_COMPONENTS:
            if component == "FIRMWARE":
                continue
            self.device_limits[component] = 8
            self.device_min_limits[component] = 3
            self.device_max_limits[component] = 14

    @staticmethod
    def _severity_weight(level: str) -> int:
        """Returns deterministic severity weight used in ranking fallback."""

        if level == "CRIT":
            return 4
        if level in {"ERRO", "ERROR"}:
            return 3
        if level == "WARN":
            return 2
        return 1

    def build_device_rankings(self) -> dict[str, list[str]]:
        """Builds per-device ranked uid lists, optionally refined by LLM."""

        stage_log("building per-device ranked pools")
        ranked: dict[str, list[str]] = {}
        for device in BASE_COMPONENTS:
            related_entries = [e for e in self.entries if related(e, device)]
            stage_log(f"rank:{device} source={len(related_entries)}")
            if not related_entries:
                ranked[device] = []
                continue
            dedup = dedupe_noise(related_entries, {device}, set())
            dedup = uniq(sorted(dedup, key=lambda x: x.timestamp))
            # Keep bounded candidate size before LLM ranking.
            prelim = sorted(
                dedup,
                key=lambda e: (
                    -self._severity_weight(e.level),
                    -1 if any(k in e.message.lower() for k in CAUSAL_KEYWORDS) else 0,
                    e.timestamp,
                ),
            )[: self.s.llm_rank_device_max_items]
            prelim = uniq(sorted(prelim, key=lambda x: x.timestamp))
            ordered_uids = [e.uid() for e in prelim]
            if self.s.llm_rank_device_logs:
                items = [
                    {"id": e.uid(), "level": e.level, "component": e.component, "line": e.render(220)}
                    for e in prelim
                ]
                stage_log(f"rank:{device} llm-start items={len(items)}")
                try:
                    llm_order = self.compressor.rank_device_logs(device, items)
                except requests.RequestException:
                    llm_order = []
                stage_log(f"rank:{device} llm-done ordered={len(llm_order)}")
                if llm_order:
                    seen = set()
                    merged: list[str] = []
                    for uid in llm_order:
                        if uid in self.by_uid and uid in ordered_uids and uid not in seen:
                            merged.append(uid)
                            seen.add(uid)
                    for uid in ordered_uids:
                        if uid not in seen:
                            merged.append(uid)
                    ordered_uids = merged
            ranked[device] = ordered_uids
            stage_log(f"rank:{device} ready={len(ordered_uids)}")
        stage_log("per-device ranked pools ready")
        return ranked

    def dump_device_rankings(self) -> None:
        """Writes ranked per-device lists to output for debugging and review."""

        payload: dict[str, Any] = {}
        for device, ordered_uids in self.device_ranked_uids.items():
            lines: list[dict[str, Any]] = []
            for pos, uid in enumerate(ordered_uids, start=1):
                entry = self.by_uid.get(uid)
                if entry is None:
                    continue
                lines.append(
                    {
                        "rank": pos,
                        "uid": uid,
                        "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "level": entry.level,
                        "component": entry.component,
                        "line": entry.render(220),
                    }
                )
            payload[device] = lines
        write_json(self.out_dir / "device_rankings.json", payload)

    def ranked_device_entries(self, device: str, limit: int, allowed_levels: set[str], crit_only: bool) -> list[LogEntry]:
        """Returns top ranked entries for a device under current stage constraints."""

        out: list[LogEntry] = []
        for uid in self.device_ranked_uids.get(device, []):
            entry = self.by_uid.get(uid)
            if entry is None:
                continue
            if crit_only and entry.level != "CRIT":
                continue
            if not crit_only and entry.level not in allowed_levels and not (device == "FIRMWARE" and entry.level == "INFO"):
                continue
            out.append(entry)
            if len(out) >= limit:
                break
        return uniq(sorted(out, key=lambda x: x.timestamp))

    def compress_entries(self, entries: list[LogEntry]) -> dict[str, str]:
        """Compresses selected entry messages with LLM in small batches."""

        if not self.s.llm_log_compression:
            return {}
        stage_log(f"compression start entries={len(entries)}")
        # Prioritize required-related and failure-severity lines for better budget usage.
        ranked = sorted(
            entries,
            key=lambda e: (
                0 if any(related(e, d) for d in self.required) else 1,
                0 if e.level in {"CRIT", "ERRO", "ERROR"} else 1,
                e.timestamp,
            ),
        )
        batch_size = self.s.llm_compression_batch_size
        target_chars = self.s.llm_compression_target_chars
        compressed: dict[str, str] = {}
        for idx in range(0, len(ranked), batch_size):
            chunk = ranked[idx : idx + batch_size]
            stage_log(f"compression batch {(idx // batch_size) + 1} size={len(chunk)}")
            payload = [
                {
                    "id": e.uid(),
                    "component": e.component,
                    "level": e.level,
                    "message": e.message,
                }
                for e in chunk
            ]
            try:
                part = self.compressor.compress_batch(payload, target_chars)
            except requests.RequestException:
                part = {}
            compressed.update(part)
        stage_log(f"compression done compressed={len(compressed)}")
        return compressed

    @staticmethod
    def tools_schema() -> list[dict[str, Any]]:
        """Returns function tool definitions for chat/completions."""

        return [
            {
                "type": "function",
                "function": {
                    "name": "search_logs",
                    "description": "Search log lines by component/keyword/level and return compact candidates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "component": {"type": ["string", "null"]},
                            "keyword": {"type": ["string", "null"]},
                            "level": {"type": ["string", "null"]},
                            "limit": {"type": "integer", "minimum": 1, "maximum": 80},
                        },
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "build_candidate",
                    "description": "Build full candidate logs under token limit using current required devices.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "count_tokens",
                    "description": "Count estimated tokens for current candidate logs before verify.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "verify_candidate",
                    "description": "Verify latest candidate with central hub and update required devices from feedback.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_status",
                    "description": "Get current attempts/required devices/token stats.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                },
            },
        ]

    def search_logs(self, args: dict[str, Any]) -> dict[str, Any]:
        """Tool: searches logs and returns compact line previews."""

        component = str(args.get("component") or "").strip().upper()
        keyword = str(args.get("keyword") or "").strip().lower()
        level = str(args.get("level") or "").strip().upper()
        limit = int(args.get("limit") or 20)

        hits = self.search_subagent.search(component=component, keyword=keyword, level=level, limit=limit)

        return {
            "count": len(hits),
            "hits": [{"id": h.uid(), "line": h.render(220)} for h in hits],
        }

    def build_candidate(self) -> dict[str, Any]:
        """Tool: builds full candidate text under current token budget."""

        stage_log(f"build_candidate start attempt={self.attempt + 1}")
        allowed_levels = set(SEVERITY_STAGES[self.severity_stage])
        for device in self.required:
            if device not in self.device_limits:
                self.device_limits[device] = 8
                self.device_min_limits[device] = 3
                self.device_max_limits[device] = 14
            self.device_non_missing_streak.setdefault(device, 0)
            self.device_locked_min.setdefault(device, False)
            self.device_last_adjustment.setdefault(device, "hold")
        for device in sorted(self.required):
            for e in device_core_packet(self.entries, device, allowed_levels):
                self.frozen_core_ids.add(e.uid())
        crit_only_devices = {d for d in self.required if self.device_first_seen_attempt.get(d, -999) == self.attempt}
        for device in sorted(self.required):
            limit = max(1, int(self.device_limits.get(device, 6)))
            for e in self.ranked_device_entries(device, limit, allowed_levels, device in crit_only_devices):
                self.frozen_core_ids.add(e.uid())
        if "FIRMWARE" in self.required:
            for e in firmware_core_packet(self.entries):
                self.frozen_core_ids.add(e.uid())
        if self.required and self.missing_repeats.get("FIRMWARE", 0) >= 1:
            for e in firmware_enrichment_packet(self.entries):
                self.frozen_core_ids.add(e.uid())

        selected = build_candidate_entries(
            self.entries,
            self.required,
            self.frozen_core_ids,
            self.force_broader_context,
            allowed_levels,
            crit_only_devices,
            self.device_limits,
            self.s.crit_context_window_minutes,
            self.s.crit_context_per_device_per_anchor,
        )
        stage_log(f"build_candidate selected={len(selected)}")
        core_ids = set(self.frozen_core_ids)
        for device in sorted(self.required):
            for e in device_core_packet(self.entries, device, allowed_levels):
                core_ids.add(e.uid())
        plain_text, plain_toks = render_and_fit(
            selected,
            self.required,
            core_ids,
            self.s.target_tokens,
            self.s.hard_limit,
            self.s.token_char_ratio,
            self.multiplier,
        )
        stage_log(f"build_candidate plain_tokens={plain_toks}")
        threshold = int(self.s.target_tokens * self.s.llm_compression_trigger_ratio)
        last_code = int(self.last_response.get("code", 0)) if isinstance(self.last_response, dict) and str(self.last_response.get("code", "")).lstrip("-").isdigit() else 0
        should_compress = (
            self.s.llm_log_compression
            and (plain_toks >= threshold or last_code == -940)
        )

        text = plain_text
        toks = plain_toks
        compression_used = False
        if should_compress:
            stage_log(f"build_candidate compression-trigger threshold={threshold}")
            compressed_map = self.compress_entries(selected)
            if compressed_map:
                compressed_text, compressed_toks = render_and_fit(
                    selected,
                    self.required,
                    core_ids,
                    self.s.target_tokens,
                    self.s.hard_limit,
                    self.s.token_char_ratio,
                    self.multiplier,
                    compressed_map,
                )
                if (
                    compressed_toks < plain_toks
                    or len([x for x in compressed_text.splitlines() if x.strip()]) > len([x for x in plain_text.splitlines() if x.strip()])
                ):
                    text = compressed_text
                    toks = compressed_toks
                    compression_used = True
                    stage_log(f"build_candidate compression-used tokens={compressed_toks}")

        self.last_text = text
        self.last_tokens = toks
        self.last_selected_entries = len(selected)
        write_json(
            self.out_dir / f"attempt_{self.attempt + 1:02d}_candidate_preview.json",
            {
                "estimated_tokens": toks,
                "required_devices": sorted(self.required),
                "device_limits": {k: self.device_limits.get(k) for k in sorted(self.required)},
                "compression_used": compression_used,
                "compression_trigger_threshold": threshold,
                "plain_tokens": plain_toks,
                "preview_lines": text.splitlines()[:25],
            },
        )
        return {
            "selected_entries": len(selected),
            "lines": len([x for x in text.splitlines() if x.strip()]),
            "estimated_tokens": toks,
            "required_devices": sorted(self.required),
            "frozen_core_entries": len(self.frozen_core_ids),
            "severity_stage": self.severity_stage,
            "allowed_levels": sorted(allowed_levels),
            "device_limits": {k: self.device_limits.get(k) for k in sorted(self.required)},
            "compression_used": compression_used,
            "plain_tokens": plain_toks,
        }

    def count_tokens(self) -> dict[str, Any]:
        """Tool: estimates tokens for current candidate and reports hard-limit status."""

        if not self.last_text:
            self.build_candidate()
        return {
            "estimated_tokens": self.last_tokens,
            "hard_limit": self.s.hard_limit,
            "target_tokens": self.s.target_tokens,
            "within_hard_limit": self.last_tokens <= self.s.hard_limit,
            "within_target": self.last_tokens <= self.s.target_tokens,
        }

    def verify_candidate(self) -> dict[str, Any]:
        """Tool: sends latest candidate to hub verify and updates feedback state."""

        if not self.last_text:
            self.build_candidate()
        if self.attempt >= self.s.max_attempts:
            return {"status": "max_attempts_reached", "attempt": self.attempt}

        self.attempt += 1
        req_disp = ", ".join(sorted(self.required)) if self.required else "-"
        lines = len([x for x in self.last_text.splitlines() if x.strip()])
        print(
            f"[attempt {self.attempt}/{self.s.max_attempts}] selected={self.last_selected_entries} "
            f"lines={lines} tokens~{self.last_tokens}/{self.s.target_tokens} required_devices={req_disp}"
        )

        (self.out_dir / f"attempt_{self.attempt:02d}_logs.txt").write_text(self.last_text, encoding="utf-8")
        write_json(
            self.out_dir / f"attempt_{self.attempt:02d}_candidate.json",
            {
                "attempt": self.attempt,
                "estimated_tokens": self.last_tokens,
                "required_devices": sorted(self.required),
                "frozen_core_entries": len(self.frozen_core_ids),
            },
        )

        data = self.hub.verify(self.last_text)
        stage_log(f"verify done attempt={self.attempt} code={data.get('code')}")
        write_json(self.out_dir / f"attempt_{self.attempt:02d}_verify.json", data)
        self.last_response = data
        # Side mission extraction: "tokens of wrong answers are characters".
        for ch in extract_side_chars(data):
            if ch not in self.side_seen_chars:
                self.side_seen_chars.add(ch)
                self.side_chars.append(ch)
        blob = json.dumps(data, ensure_ascii=False)
        m = re.search(r"\{FLG:[^}]+\}", blob)
        self.flag = m.group(0) if m else None
        missing = extract_missing(data)
        newly_seen = [d for d in missing if d not in self.required]
        self.required.update(missing)
        for device in newly_seen:
            self.device_first_seen_attempt[device] = self.attempt
        for device in self.required:
            if device not in self.device_limits:
                self.device_limits[device] = 8
                self.device_min_limits[device] = 3
                self.device_max_limits[device] = 14
            self.device_non_missing_streak.setdefault(device, 0)
            self.device_locked_min.setdefault(device, False)
            self.device_last_adjustment.setdefault(device, "hold")
        code = int(data.get("code", 0)) if str(data.get("code", "")).lstrip("-").isdigit() else 0
        self.force_broader_context = code == -960
        if code == -960 and self.severity_stage < 2:
            self.severity_stage += 1
        if code == -960:
            for device in sorted(self.required):
                self.device_limits[device] = min(self.device_max_limits[device], self.device_limits[device] + 1)
                self.device_last_adjustment[device] = "up"
        for device in missing:
            self.missing_repeats[device] = self.missing_repeats.get(device, 0) + 1
        for device in list(self.missing_repeats.keys()):
            if device not in missing:
                self.missing_repeats[device] = 0
        # If central keeps asking for a component, broaden severity stage even without -960.
        if any(count >= 2 for count in self.missing_repeats.values()) and self.severity_stage < 2:
            self.severity_stage += 1

        # Per-device minimization loop:
        # - when missing persists -> increase line budget
        # - when device is stable as non-missing for 2 rounds -> probe one line down
        # - if missing returns right after down-probe -> lock minimum and go one step up
        for device in sorted(self.required):
            current = self.device_limits[device]
            min_limit = self.device_min_limits[device]
            max_limit = self.device_max_limits[device]
            last_adj = self.device_last_adjustment.get(device, "hold")
            if device in missing:
                self.device_non_missing_streak[device] = 0
                if last_adj == "down":
                    self.device_limits[device] = min(max_limit, current + 1)
                    self.device_locked_min[device] = True
                else:
                    step = 2 if device == "FIRMWARE" else 1
                    self.device_limits[device] = min(max_limit, current + step)
                self.device_last_adjustment[device] = "up"
                continue

            self.device_non_missing_streak[device] = self.device_non_missing_streak.get(device, 0) + 1
            if self.device_locked_min.get(device, False):
                self.device_last_adjustment[device] = "hold"
                continue
            if self.device_non_missing_streak[device] >= 2 and current > min_limit:
                self.device_limits[device] = current - 1
                self.device_last_adjustment[device] = "down"
                self.device_non_missing_streak[device] = 0
            else:
                self.device_last_adjustment[device] = "hold"

        msg = str(data.get("message", ""))[:170]
        print(f"[attempt {self.attempt}] {'FLAG' if self.flag else 'RETRY'} code={data.get('code')} missing={', '.join(sorted(missing)) if missing else '-'} msg={msg}")
        print(
            f"[attempt {self.attempt}] state required_devices="
            f"{', '.join(sorted(self.required)) if self.required else '-'} "
            f"severity_stage={self.severity_stage} levels={','.join(SEVERITY_STAGES[self.severity_stage])} "
            f"fw_repeat={self.missing_repeats.get('FIRMWARE', 0)}"
        )
        if self.side_chars:
            joined = "".join(self.side_chars)
            print(f"[attempt {self.attempt}] side_chars={joined}")
            write_json(
                self.out_dir / "side_mission_progress.json",
                {
                    "chars_unique_order": joined,
                    "flag_candidates": [joined, f"FLAG{{{joined}}}", f"{{FLG:{joined}}}"],
                    "updated_at": datetime.now().isoformat(timespec="seconds"),
                },
            )
        if self.required:
            limits_str = ", ".join(
                f"{d}:{self.device_limits.get(d, '-')}{'*' if self.device_locked_min.get(d, False) else ''}"
                for d in sorted(self.required)
            )
            print(f"[attempt {self.attempt}] limits {limits_str}")

        ov = re.search(r"Token usage:\s*(\d+)\s*/\s*(\d+)", str(data.get("message", "")))
        if ov:
            used = int(ov.group(1))
            local = max(1, token_est(self.last_text, self.s.token_char_ratio, 1.0))
            self.multiplier = max(self.multiplier, (used / local) * 1.03)

        return {
            "attempt": self.attempt,
            "code": data.get("code"),
            "missing": sorted(missing),
            "required_devices": sorted(self.required),
            "device_limits": {k: self.device_limits.get(k) for k in sorted(self.required)},
            "side_chars": "".join(self.side_chars),
            "flag": self.flag,
        }

    def get_status(self) -> dict[str, Any]:
        """Tool: returns compact status."""

        return {
            "attempt": self.attempt,
            "max_attempts": self.s.max_attempts,
            "required_devices": sorted(self.required),
            "has_candidate": bool(self.last_text),
            "has_flag": bool(self.flag),
            "last_tokens": self.last_tokens,
        }

    def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Dispatches tool by function name."""

        if name == "search_logs":
            return self.search_logs(args)
        if name == "build_candidate":
            return self.build_candidate()
        if name == "count_tokens":
            return self.count_tokens()
        if name == "verify_candidate":
            return self.verify_candidate()
        if name == "get_status":
            return self.get_status()
        return {"error": f"Unknown tool: {name}"}


def run_agent() -> None:
    """Runs always-agentic function-calling solver."""

    s = Settings()
    out_dir = s.output_dir()
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    hub = HubClient(s)
    stage_log("download log start")
    raw = hub.download_log()
    stage_log("download log done")
    (out_dir / "raw_failure.log").write_text(raw, encoding="utf-8")
    stage_log("parse log start")
    entries = parse_log(raw)
    stage_log(f"parse log done entries={len(entries)}")
    if not entries:
        raise RuntimeError("No log entries parsed.")

    write_json(
        out_dir / "dataset_summary.json",
        {
            "entries_total": len(entries),
            "estimated_tokens_total": token_est(raw, s.token_char_ratio, 1.0),
            "mode": "function_calling",
            "provider": s.llm_provider(),
            "model": s.llm_model,
        },
    )
    write_json(
        out_dir / "raw_summary.json",
        {
            "downloaded_at": datetime.now().isoformat(timespec="seconds"),
            "raw_lines": len(raw.splitlines()),
            "raw_chars": len(raw),
            "raw_estimated_tokens": token_est(raw, s.token_char_ratio, 1.0),
        },
    )

    toolbox = Toolbox(s, hub, entries, out_dir)
    toolbox.dump_device_rankings()
    stage_log("device rankings saved to output/device_rankings.json")
    chat = ChatClient(s)
    tools = Toolbox.tools_schema()
    print(f"[agent] mode=function_calling provider={s.llm_provider()} model={s.llm_model} max_steps={s.agent_max_steps} max_attempts={s.max_attempts}")

    planner_prompt = (
        "Solve the failure task with tools only.\n"
        "Workflow per cycle:\n"
        "1) build_candidate\n"
        "2) count_tokens\n"
        "3) verify_candidate\n"
        "4) If feedback shows missing devices, repeat cycle.\n"
        "Keep full cumulative logs, preserve chronology, and stay under token limit."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "You are an exact function-calling agent. Use tools only."},
        {"role": "user", "content": planner_prompt},
    ]

    response = chat.complete(messages, tools)
    for _ in range(s.agent_max_steps):
        choice = (response.get("choices") or [{}])[0]
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        tool_calls = message.get("tool_calls", []) if isinstance(message, dict) else []

        messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": tool_calls or None})
        if not tool_calls:
            if toolbox.flag or toolbox.attempt >= s.max_attempts:
                break
            messages.append({"role": "user", "content": "Continue. Call build_candidate, then count_tokens, then verify_candidate."})
            response = chat.complete(messages, tools)
            continue

        for call in tool_calls:
            fn = call.get("function", {})
            name = str(fn.get("name", ""))
            raw_args = str(fn.get("arguments", "{}") or "{}")
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                args = {}
            result = toolbox.execute(name, args if isinstance(args, dict) else {})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.get("id"),
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

        response = chat.complete(messages, tools)
        if toolbox.flag or toolbox.attempt >= s.max_attempts:
            break

    while not toolbox.flag and toolbox.attempt < s.max_attempts:
        toolbox.build_candidate()
        toolbox.verify_candidate()

    write_json(
        out_dir / "result.json",
        {
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "task": s.task_name,
            "mode": "function_calling",
            "provider": s.llm_provider(),
            "model": s.llm_model,
            "flag": toolbox.flag,
            "attempts_used": toolbox.attempt,
            "final_response": toolbox.last_response,
        },
    )
    (out_dir / "final_logs.txt").write_text(toolbox.last_text, encoding="utf-8")
    print(toolbox.flag if toolbox.flag else "Nie uzyskano flagi. Sprawdz output/attempt_*_verify.json oraz final_logs.txt.")


def main() -> None:
    """Runs script entrypoint."""

    run_agent()


if __name__ == "__main__":
    """Executes script when run directly."""

    main()
