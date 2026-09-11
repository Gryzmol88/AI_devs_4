"""Side-quest bootstrap for lesson4: probe "deleted but still in HEAD" clues."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

try:
    from .config import SideQuestSettings
except ImportError:
    from config import SideQuestSettings


FLAG_PATTERN = re.compile(r"\{FLG:[^}]+\}")


def _extract_links(markdown_text: str, base_url: str) -> set[str]:
    """Extract absolute URLs from markdown links and include directives."""

    urls: set[str] = set()
    for rel in re.findall(r'\[include\s+file="([^"]+)"\]', markdown_text, flags=re.IGNORECASE):
        urls.add(urljoin(base_url, rel.strip()))
    for rel in re.findall(r"\[[^\]]*\]\(([^)\s]+)\)", markdown_text):
        candidate = rel.strip()
        if candidate.startswith("http://") or candidate.startswith("https://"):
            urls.add(candidate)
        else:
            urls.add(urljoin(base_url, candidate))
    return urls


def _extract_versions_from_history(markdown_text: str) -> list[str]:
    """Extract version-like strings, for example `7.024`, from markdown content."""

    versions = re.findall(r"\b\d+\.\d{3}\b", markdown_text)
    out: list[str] = []
    for value in versions:
        if value not in out:
            out.append(value)
    return out


def _build_candidate_urls(index_url: str, index_text: str) -> list[str]:
    """Build likely URLs where removed Annex I or old docs may still exist."""

    base_candidates = {
        index_url,
        urljoin(index_url, "zalacznik-I.md"),
        urljoin(index_url, "zalacznik-i.md"),
        urljoin(index_url, "zalacznik-I.txt"),
        urljoin(index_url, "zalacznik-I-old.md"),
        urljoin(index_url, "zalacznik-I.bak.md"),
        urljoin(index_url, "annex-I.md"),
    }

    versions = _extract_versions_from_history(index_text)
    for ver in versions:
        compact = ver.replace(".", "_")
        base_candidates.add(urljoin(index_url, f"index-v{ver}.md"))
        base_candidates.add(urljoin(index_url, f"index-{ver}.md"))
        base_candidates.add(urljoin(index_url, f"index_{compact}.md"))
        base_candidates.add(urljoin(index_url, f"index.md?version={ver}"))
        base_candidates.add(urljoin(index_url, f"index.md?v={ver}"))
        base_candidates.add(urljoin(index_url, f"index.md?rev={ver}"))

    base_candidates.update(_extract_links(index_text, index_url))
    return sorted(base_candidates)


def _scan_for_flag(data: Any) -> str | None:
    """Return first flag found in serialized object or text."""

    if isinstance(data, (dict, list)):
        text = json.dumps(data, ensure_ascii=False)
    else:
        text = str(data)
    found = FLAG_PATTERN.search(text)
    return found.group(0) if found else None


def _request_once(method: str, url: str, timeout: int) -> dict[str, Any]:
    """Send one HTTP request and return normalized response record."""

    try:
        response = requests.request(method=method, url=url, timeout=timeout)
        body_text = response.text
        try:
            body_json: Any | None = response.json()
        except Exception:
            body_json = None
        flag = _scan_for_flag(body_json if body_json is not None else body_text)
        header_flag = _scan_for_flag(dict(response.headers))
        return {
            "method": method,
            "url": url,
            "status_code": response.status_code,
            "ok_http": response.ok,
            "headers": dict(response.headers),
            "body_text": body_text[:4000],
            "body_json": body_json,
            "flag": flag or header_flag,
        }
    except Exception as error:  # noqa: BLE001
        return {
            "method": method,
            "url": url,
            "status_code": None,
            "ok_http": False,
            "headers": {},
            "body_text": "",
            "body_json": None,
            "flag": None,
            "error": str(error),
        }


def main() -> None:
    """Probe documentation endpoints and variants to discover side-quest flag."""

    settings = SideQuestSettings()
    output_dir = Path(settings.SAVE_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)

    index_record = _request_once("GET", settings.DOC_INDEX_URL, settings.REQUEST_TIMEOUT_SECONDS)
    if not index_record.get("ok_http"):
        (output_dir / "probe_results.json").write_text(
            json.dumps({"error": "Could not fetch index", "record": index_record}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("Could not fetch index.md. See output/probe_results.json")
        return

    index_text = str(index_record.get("body_text", ""))
    candidates = _build_candidate_urls(settings.DOC_INDEX_URL, index_text)

    all_records: list[dict[str, Any]] = [index_record]
    for url in candidates:
        if settings.USE_HEAD_METHOD:
            head_record = _request_once("HEAD", url, settings.REQUEST_TIMEOUT_SECONDS)
            all_records.append(head_record)
            if head_record.get("flag"):
                break

        get_record = _request_once("GET", url, settings.REQUEST_TIMEOUT_SECONDS)
        all_records.append(get_record)
        if get_record.get("flag"):
            break

    result = {
        "index_url": settings.DOC_INDEX_URL,
        "attempts": len(all_records),
        "records": all_records,
    }
    (output_dir / "probe_results.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    found_flag: str | None = None
    found_record: dict[str, Any] | None = None
    for record in all_records:
        if record.get("flag"):
            found_flag = str(record["flag"])
            found_record = record
            break

    if found_flag and found_record:
        print(f"FLAG FOUND: {found_flag}")
        print(json.dumps(found_record, ensure_ascii=False, indent=2))
    else:
        print("No flag found. Inspect lesson4_misja_poboczna/output/probe_results.json")


if __name__ == "__main__":
    main()
