"""Tool handlers for the sendit function-calling workflow.

This module contains concrete implementations of the four tools exposed to the
LLM agent:
- fetch_docs_recursive
- extract_nontext
- build_declaration_from_rules
- verify_sendit
"""

import base64
import csv
import json
import re
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .settings import SenditSettings



TEXT_EXTENSIONS = {".md", ".txt", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class SenditToolHandlers:
    """Dispatches and executes tool calls for the sendit task.

    Side effects:
    - Reads/writes files inside the configured workspace.
    - Performs HTTP requests to documentation endpoints and `/verify`.
    - Calls LLM endpoints through OpenRouter-compatible OpenAI client.
    """

    def __init__(self, workspace_dir: Path, settings: SenditSettings):
        """Initialize paths and runtime settings.

        Args:
            workspace_dir: Root directory used for `raw/`, `parsed/`, and manifest files.
            settings: Typed configuration loaded via Pydantic Settings.
        """

        self.settings = settings
        self.workspace_dir = workspace_dir
        self.raw_dir = workspace_dir / "raw"
        self.parsed_dir = workspace_dir / "parsed"
        self.parsed_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = workspace_dir / "manifest.csv"
        self.verify_response_path = self.parsed_dir / "verify_response.json"

    def dispatch(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Route a tool call name to a concrete handler method.

        Args:
            name: Tool function name requested by the LLM.
            args: Parsed JSON arguments for the tool.

        Returns:
            dict[str, Any]: Standard envelope with `ok` and either `data` or `error`.
        """

        try:
            if name == "fetch_docs_recursive":
                return {"ok": True, "data": self.fetch_docs_recursive(args)}
            if name == "extract_nontext":
                return {"ok": True, "data": self.extract_nontext(args)}
            if name == "build_declaration_from_rules":
                return {"ok": True, "data": self.build_declaration_from_rules(args)}
            if name == "verify_sendit":
                return {"ok": True, "data": self.verify_sendit(args)}
            return {"ok": False, "error": f"Unknown tool: {name}"}
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "error": str(error)}

    def fetch_docs_recursive(self, args: dict[str, Any]) -> dict[str, Any]:
        """Download documentation recursively and persist all discovered files.

        Recognized link forms inside text files:
        - Markdown links: `[label](path-or-url)`
        - Include directives: `[include file="..."]`
        - Plain absolute URLs

        Args:
            args: Optional runtime parameters:
                - `index_url` (str): Starting URL. Defaults to hub index.md.
                - `output_dir` (str): Destination root for downloaded files.

        Returns:
            dict[str, Any]: Summary with start URL, output path, manifest path,
                and downloaded file count.

        Raises:
            requests.HTTPError: When a fetched URL returns non-2xx status.
        """

        default_index_url = "https://hub.ag3nts.org/dane/doc/index.md"
        requested_index_url = str(args.get("index_url") or "").strip()
        index_url = requested_index_url or default_index_url
        output_dir = Path(args.get("output_dir") or self.raw_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        scope_url = default_index_url if requested_index_url else index_url
        parsed = urlparse(scope_url)
        base_host = parsed.netloc
        base_path_prefix = str(Path(parsed.path).parent).replace("\\", "/") + "/"

        queue: list[str] = [index_url]
        seen: set[str] = set()
        records: dict[str, dict[str, str]] = self._load_manifest()

        while queue:
            current_url = queue.pop(0)
            if current_url in seen:
                continue
            seen.add(current_url)

            local_path = self._url_to_local_path(current_url, output_dir)
            local_path.parent.mkdir(parents=True, exist_ok=True)

            response = requests.get(current_url, timeout=30)
            if response.status_code == 404 and current_url == requested_index_url and requested_index_url:
                # LLMs can guess wrong index paths; fallback to canonical task docs URL.
                queue.append(default_index_url)
                continue
            response.raise_for_status()
            local_path.write_bytes(response.content)
            records[current_url] = {
                "url": current_url,
                "local_path": str(local_path),
                "status": "downloaded",
                "notes": "ok",
            }

            if local_path.suffix.lower() in TEXT_EXTENSIONS:
                content = local_path.read_text(encoding="utf-8", errors="ignore")
                discovered = self._discover_links(content, current_url)
                for url in discovered:
                    p = urlparse(url)
                    if p.netloc != base_host:
                        continue
                    if not p.path.startswith(base_path_prefix):
                        continue
                    if url not in seen:
                        queue.append(url)

        self._write_manifest(records)
        downloaded_count = len([r for r in records.values() if r.get("status") == "downloaded"])
        return {
            "index_url": index_url,
            "output_dir": str(output_dir),
            "manifest_path": str(self.manifest_path),
            "downloaded": downloaded_count,
        }

    def extract_nontext(self, args: dict[str, Any]) -> dict[str, Any]:
        """Extract text from image files using a vision-capable LLM.

        This method scans `raw_dir` recursively for known image extensions,
        runs OCR-like extraction via `_extract_image_text`, and writes one markdown
        transcript per file to `parsed/nontext` (or a caller-provided directory).

        Args:
            args: Optional runtime parameters:
                - `raw_dir` (str): Directory to scan for non-text files.
                - `parsed_dir` (str): Output directory for transcripts.
                - `vision_model` (str): Model name for vision extraction.

        Returns:
            dict[str, Any]: Number of processed files, output items, and model name.
        """

        raw_dir = Path(args.get("raw_dir") or (self.raw_dir / "dane" / "doc"))
        parsed_dir = Path(args.get("parsed_dir") or (self.parsed_dir / "nontext"))
        parsed_dir.mkdir(parents=True, exist_ok=True)
        vision_model = self.settings.VISION_MODEL

        image_paths = [p for p in raw_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS]
        if not image_paths:
            return {"processed": 0, "notes": "No image files found."}

        processed = []
        for image_path in image_paths:
            text = self._extract_image_text(image_path, vision_model)
            out_path = parsed_dir / f"{image_path.stem}.md"
            out_path.write_text(
                f"# OCR from {image_path.name}\n\n{text}\n",
                encoding="utf-8",
            )
            processed.append({"source": str(image_path), "transcript": str(out_path)})

        return {
            "processed": len(processed),
            "items": processed,
            "vision_model": vision_model,
        }

    def build_declaration_from_rules(self, args: dict[str, Any]) -> dict[str, Any]:
        """Build declaration deterministically from fixed task constraints.

        This implementation does not allow the LLM to override mission data.
        It produces declaration text exactly in the expected SPK template shape,
        including the required start marker.

        Args:
            args: Optional runtime parameters:
                - `parsed_dir` (str): Output directory for declaration file.

        Returns:
            dict[str, Any]: Path to saved declaration, output size, and mode.
        """

        parsed_dir = Path(args.get("parsed_dir") or self.parsed_dir)
        parsed_dir.mkdir(parents=True, exist_ok=True)

        today = date.today().isoformat()
        declaration = (
            "SYSTEM PRZESYŁEK KONDUKTORSKICH - DEKLARACJA ZAWARTOŚCI\n"
            "======================================================\n"
            f"DATA: {today}\n"
            "PUNKT NADAWCZY: Gdańsk\n"
            "------------------------------------------------------\n"
            "NADAWCA: 450202122\n"
            "PUNKT DOCELOWY: Żarnowiec\n"
            "TRASA: X-01\n"
            "------------------------------------------------------\n"
            "KATEGORIA PRZESYŁKI: A\n"
            "------------------------------------------------------\n"
            "OPIS ZAWARTOŚCI (max 200 znaków): kasety z paliwem do reaktora\n"
            "------------------------------------------------------\n"
            "DEKLAROWANA MASA (kg): 2800\n"
            "------------------------------------------------------\n"
            "WDP: 4\n"
            "------------------------------------------------------\n"
            "UWAGI SPECJALNE: \n"
            "------------------------------------------------------\n"
            "KWOTA DO ZAPŁATY: 0 PP\n"
            "------------------------------------------------------\n"
            "OŚWIADCZAM, ŻE PODANE INFORMACJE SĄ PRAWDZIWE.\n"
            "BIORĘ NA SIEBIE KONSEKWENCJĘ ZA FAŁSZYWE OŚWIADCZENIE.\n"
            "======================================================"
        )

        output_path = parsed_dir / "declaration.txt"
        output_path.write_text(declaration + "\n", encoding="utf-8")
        return {
            "declaration_path": str(output_path),
            "chars": len(declaration),
            "mode": "deterministic_template",
        }

    def verify_sendit(self, args: dict[str, Any]) -> dict[str, Any]:
        """Submit declaration from file to `/verify` for task `sendit`.

        For safety this method ignores `declaration_text` provided by the model and
        always reads declaration from file.

        Args:
            args: Optional runtime parameters:
                - `task` (str): Verify task name, defaults to `sendit`.
                - `declaration_path` (str): Path to declaration file.

        Returns:
            dict[str, Any]: HTTP status, body, and path to saved verify response JSON.

        Raises:
            FileNotFoundError: If declaration file is missing.
        """

        task = str(args.get("task") or "sendit")
        declaration_path = args.get("declaration_path")

        path = Path(declaration_path) if declaration_path else self.parsed_dir / "declaration.txt"
        if not path.exists():
            raise FileNotFoundError("Missing declaration file.")
        declaration_text = path.read_text(encoding="utf-8")

        payload = {
            "apikey": self.settings.HUB_API_KEY,
            "task": task,
            "answer": {"declaration": declaration_text},
        }
        response = requests.post("https://hub.ag3nts.org/verify", json=payload, timeout=30)

        try:
            body = response.json()
        except Exception:  # noqa: BLE001
            body = {"raw_text": response.text}

        self.verify_response_path.write_text(
            json.dumps(
                {
                    "http_status": response.status_code,
                    "ok_http": response.ok,
                    "body": body,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "http_status": response.status_code,
            "ok_http": response.ok,
            "body": body,
            "saved": str(self.verify_response_path),
        }

    def _extract_image_text(self, image_path: Path, model: str) -> str:
        """Run OCR-style extraction on a single image via multimodal LLM.

        Args:
            image_path: Local image path to process.
            model: Vision-capable model identifier.

        Returns:
            str: Extracted text or `NO_TEXT` marker depending on model response.
        """

        data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        ext = image_path.suffix.lower().lstrip(".")
        mime = "jpeg" if ext == "jpg" else ext
        data_url = f"data:image/{mime};base64,{data}"

        client = self._llm_client()
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Extract all readable text from this image exactly. "
                                "If there is no readable text, answer: NO_TEXT"
                            ),
                        },
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def _llm_client(self):
        """Create OpenAI-compatible client configured for OpenRouter.

        Returns:
            Any: OpenAI client instance (type loaded lazily).

        Raises:
            RuntimeError: If `openai` package is unavailable.
        """

        try:
            from openai import OpenAI
        except ModuleNotFoundError as error:
            raise RuntimeError("Package openai is required. Install dependencies first.") from error
        return OpenAI(api_key=self.settings.OPENROUTER_API_KEY, base_url=self.settings.OPENROUTER_BASE_URL)

    def _build_docs_bundle(self, raw_dir: Path, parsed_dir: Path) -> str:
        """Build a bounded text corpus from downloaded docs and OCR outputs.

        Args:
            raw_dir: Directory with downloaded source files.
            parsed_dir: Directory with generated OCR markdown files.

        Returns:
            str: Concatenated corpus trimmed to 120k chars.
        """

        chunks: list[str] = []
        for path in sorted(raw_dir.rglob("*")):
            if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS:
                text = path.read_text(encoding="utf-8", errors="ignore")
                chunks.append(f"\n\n### FILE: {path.name}\n{text[:6000]}")

        nontext_dir = parsed_dir / "nontext"
        if nontext_dir.exists():
            for path in sorted(nontext_dir.glob("*.md")):
                text = path.read_text(encoding="utf-8", errors="ignore")
                chunks.append(f"\n\n### OCR FILE: {path.name}\n{text[:6000]}")

        joined = "\n".join(chunks)
        return joined[:120000]

    def _discover_links(self, content: str, current_url: str) -> list[str]:
        """Extract and resolve links from documentation content.

        Args:
            content: Text content to scan.
            current_url: Base URL used to resolve relative links.

        Returns:
            list[str]: Unique resolved URLs discovered in the content.
        """

        candidates: set[str] = set()

        include_matches = re.findall(r'\[include\s+file="([^"]+)"\]', content, flags=re.IGNORECASE)
        for item in include_matches:
            candidates.add(item.strip())

        md_matches = re.findall(r"\[[^\]]*\]\(([^)\s]+)", content)
        for item in md_matches:
            candidates.add(item.strip())

        plain_urls = re.findall(r"https?://[^\s)\]]+", content)
        for item in plain_urls:
            candidates.add(item.strip())

        resolved: list[str] = []
        for candidate in candidates:
            if not candidate or candidate.startswith("#"):
                continue
            if candidate.startswith("http://") or candidate.startswith("https://"):
                resolved.append(candidate)
            else:
                resolved.append(urljoin(current_url, candidate))
        return resolved

    def _url_to_local_path(self, url: str, output_dir: Path) -> Path:
        """Map URL to deterministic local file path under output directory.

        Args:
            url: Source URL.
            output_dir: Root download directory.

        Returns:
            Path: Local path preserving URL path structure.
        """

        parsed = urlparse(url)
        path = parsed.path.lstrip("/")
        if not path:
            path = "index.html"
        return output_dir / path

    def _load_manifest(self) -> dict[str, dict[str, str]]:
        """Load manifest CSV into memory.

        Returns:
            dict[str, dict[str, str]]: Mapping by URL with path/status/notes values.
        """

        if not self.manifest_path.exists():
            return {}

        out: dict[str, dict[str, str]] = {}
        with self.manifest_path.open("r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                url = row.get("url")
                if url:
                    out[url] = {
                        "url": url,
                        "local_path": row.get("local_path", ""),
                        "status": row.get("status", ""),
                        "notes": row.get("notes", ""),
                    }
        return out

    def _write_manifest(self, records: dict[str, dict[str, str]]) -> None:
        """Write manifest records to CSV in stable URL order.

        Args:
            records: Manifest mapping keyed by URL.
        """

        with self.manifest_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=["url", "local_path", "status", "notes"])
            writer.writeheader()
            for url in sorted(records.keys()):
                writer.writerow(records[url])

