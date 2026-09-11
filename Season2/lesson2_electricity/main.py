from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import requests
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator, model_validator

VERIFY_URL = "https://hub.ag3nts.org/verify"
TASK_NAME = "electricity"
SOLVED_BOARD_URL = "https://hub.ag3nts.org/i/solved_electricity.png"

BASE_DIR = Path(__file__).resolve().parent
SEASON2_DIR = BASE_DIR.parent
PROJECT_ROOT = SEASON2_DIR.parent
OUTPUT_DIR = BASE_DIR / "output"

DEFAULT_ORCHESTRATOR_MODEL = "openai/gpt-4.1-mini"
DEFAULT_VISION_MODEL = "google/gemini-3-flash-preview"
DEFAULT_VISION_MODELS_CSV = "google/gemini-3-flash-preview"
DEFAULT_ALLOW_VISION_FALLBACK = False
FORCED_MAX_AGENT_ROUNDS = 10

DIRECTION_ORDER = ["U", "R", "D", "L"]
ROTATE_RIGHT_MAP = {"U": "R", "R": "D", "D": "L", "L": "U"}


class AppConfig(BaseModel):
    """Trzyma konfigurację agenta i limity bezpieczeństwa.

    Najważniejsze pola:
    - `orchestrator_model`: model prowadzący pętlę function-calling,
    - `vision_models`: lista modeli do odczytu planszy (fallback),
    - `dry_run`: tryb bez wykonywania realnych obrotów.
    """

    hub_api_key: str
    openrouter_api_key: str
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    verify_url: str = VERIFY_URL
    task_name: str = TASK_NAME
    board_url_template: str = "https://hub.ag3nts.org/data/{apikey}/electricity.png"
    solved_board_url: str = SOLVED_BOARD_URL

    orchestrator_model: str = DEFAULT_ORCHESTRATOR_MODEL
    vision_models: list[str] = Field(default_factory=lambda: [DEFAULT_VISION_MODEL])

    request_timeout_seconds: int = Field(default=60, ge=5, le=300)
    vision_reads_current: int = Field(default=2, ge=1, le=6)
    vision_reads_target: int = Field(default=3, ge=1, le=8)
    vision_reads_repair: int = Field(default=3, ge=1, le=8)
    vision_target_audit_reads: int = Field(default=6, ge=2, le=20)
    tiles_binarize_threshold: int = Field(default=190, ge=80, le=245)
    max_agent_rounds: int = Field(default=16, ge=2, le=80)
    max_finalize_steps: int = Field(default=8, ge=0, le=80)
    max_total_rotations: int = Field(default=120, ge=1, le=2000)
    default_batch_size: int = Field(default=4, ge=1, le=30)
    allow_vision_fallback: bool = DEFAULT_ALLOW_VISION_FALLBACK
    dry_run: bool = True

    @field_validator("hub_api_key", "openrouter_api_key")
    @classmethod
    def _non_empty_secret(cls, value: str) -> str:
        """Pilnuje, że wymagane sekrety są niepuste."""

        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Wymagana wartość nie może być pusta.")
        return cleaned

    @field_validator("vision_models")
    @classmethod
    def _vision_models_not_empty(cls, value: list[str]) -> list[str]:
        """Normalizuje i waliduje listę modeli vision."""

        models = [v.strip() for v in value if v.strip()]
        if not models:
            raise ValueError("Lista vision_models nie może być pusta.")
        return models

    @field_validator("board_url_template")
    @classmethod
    def _template_has_placeholder(cls, value: str) -> str:
        """Wymusza placeholder `{apikey}` w URL planszy bieżącej."""

        if "{apikey}" not in value:
            raise ValueError("board_url_template musi zawierać {apikey}.")
        return value


class CellPosition(BaseModel):
    """Pozycja pola 3x3 z helperem do formatu API."""

    row: int = Field(..., ge=1, le=3)
    col: int = Field(..., ge=1, le=3)

    def label(self) -> str:
        """Zwraca etykietę `AxB` wymaganą przez hub verify."""

        return f"{self.row}x{self.col}"


class BoardCell(BaseModel):
    """Opis jednego pola przez kierunki portów kabla (U/R/D/L)."""

    position: CellPosition
    ports: list[Literal["U", "R", "D", "L"]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize_ports(self) -> "BoardCell":
        """Usuwa duplikaty i sortuje porty w kolejności URDL."""

        self.ports = sorted(set(self.ports), key=DIRECTION_ORDER.index)
        return self


class BoardState(BaseModel):
    """Pełny odczyt planszy 3x3 zwrócony przez model vision."""

    source: Literal["current", "target"]
    cells: list[BoardCell]

    @model_validator(mode="after")
    def _full_grid(self) -> "BoardState":
        """Sprawdza kompletność 9 pozycji bez duplikatów."""

        labels = [c.position.label() for c in self.cells]
        expected = {f"{r}x{c}" for r in range(1, 4) for c in range(1, 4)}
        if len(labels) != 9 or set(labels) != expected:
            raise ValueError("BoardState musi zawierać dokładnie pola 1x1..3x3.")
        return self

    def by_label(self) -> dict[str, BoardCell]:
        """Ułatwia lookup pola po etykiecie `AxB`."""

        return {c.position.label(): c for c in self.cells}


class PlannedMove(BaseModel):
    """Ruch logiczny: ile obrotów w prawo wykonać dla jednego pola."""

    position: CellPosition
    turns_right: int = Field(..., ge=1, le=3)
    reason: str = ""


class RotationPlan(BaseModel):
    """Plan przekształcenia current->target wyliczony deterministycznie."""

    strategy_summary: str
    moves: list[PlannedMove] = Field(default_factory=list)

    def expanded_rotation_labels(self) -> list[str]:
        """Rozwija ruchy do pojedynczych komend `rotate`."""

        labels: list[str] = []
        for move in self.moves:
            labels.extend([move.position.label()] * move.turns_right)
        return labels


class VisionPlannedMove(BaseModel):
    """Pomocniczy model walidacji ruchów zwróconych przez planner vision."""

    row: int = Field(..., ge=1, le=3)
    col: int = Field(..., ge=1, le=3)
    turns_right: int = Field(..., ge=1, le=3)
    reason: str = ""

    @model_validator(mode="before")
    @classmethod
    def _normalize_zero_based_indices(cls, data: Any) -> Any:
        """Akceptuje sporadyczne indeksowanie 0-based z vision i mapuje je na 1-based.

        Reguła:
        - jeśli `row == 0` lub `col == 0`, traktujemy wpis jako 0-based i zwiększamy
          oba indeksy o 1.
        - w pozostałych przypadkach zostawiamy dane bez zmian.
        """

        if not isinstance(data, dict):
            return data
        row = data.get("row")
        col = data.get("col")
        if isinstance(row, int) and isinstance(col, int) and (row == 0 or col == 0):
            data = dict(data)
            data["row"] = row + 1
            data["col"] = col + 1
        return data


class RotationAnswer(BaseModel):
    """Obiekt `answer` dla `/verify` w zadaniu electricity."""

    rotate: str = Field(..., pattern=r"^[1-3]x[1-3]$")


class VerifyPayload(BaseModel):
    """Pełny payload POST dla pojedynczego obrotu."""

    apikey: str
    task: str
    answer: RotationAnswer


class VerifyResponseRecord(BaseModel):
    """Jeden log request/response do `/verify`."""

    ts: str
    step: str
    request_body: dict[str, Any]
    status_code: int
    response_body: Any


class VisionTableBox(BaseModel):
    """Bounding box całej tabeli/szachownicy 3x3."""

    left_pct: float
    top_pct: float
    right_pct: float
    bottom_pct: float
    model_name: str = ""

    @model_validator(mode="after")
    def _validate_box(self) -> "VisionTableBox":
        for value in (self.left_pct, self.top_pct, self.right_pct, self.bottom_pct):
            if not (0.0 <= value <= 1.0):
                raise ValueError("Wartości *_pct muszą być w zakresie 0..1.")
        if self.right_pct <= self.left_pct or self.bottom_pct <= self.top_pct:
            raise ValueError("Nieprawidłowy bbox tabeli.")
        return self


class ToolCallResult(BaseModel):
    """Ujednolica odpowiedź lokalnego tool handlera dla modelu orchestratora."""

    ok: bool
    tool_name: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class RuntimeState(BaseModel):
    """Stan sesji utrzymywany między kolejnymi wywołaniami narzędzi."""

    current_board: BoardState | None = None
    target_board: BoardState | None = None
    current_plan: RotationPlan | None = None
    pending_rotations: list[str] = Field(default_factory=list)
    total_rotations_sent: int = 0
    last_feedback: str = ""
    flag: str | None = None
    last_current_image: bytes | None = None
    last_target_image: bytes | None = None
    no_progress_rotation_rounds: int = 0
    force_full_remap: bool = False


class SolveResult(BaseModel):
    """Raport końcowy zapisywany do `output/result.json`."""

    ok: bool
    dry_run: bool
    flag: str | None = None
    total_rotations_sent: int = 0
    tool_rounds_used: int = 0
    warnings: list[str] = Field(default_factory=list)


def load_env_files() -> None:
    """Ładuje `.env` z roota i `Season2/.env`."""

    load_dotenv(PROJECT_ROOT / ".env")
    load_dotenv(SEASON2_DIR / ".env")
    load_dotenv()


def now_iso() -> str:
    """Timestamp ISO do logów JSONL."""

    return datetime.now().isoformat(timespec="seconds")


def log(message: str) -> None:
    """Wypisuje prosty log etapów wykonywania programu."""

    print(f"[{now_iso()}] {message}")


def write_json(path: Path, payload: Any) -> None:
    """Zapisuje sformatowany JSON do pliku."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, payload: Any) -> None:
    """Dopisuje rekord JSON jako nową linię."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def write_binary(path: Path, payload: bytes) -> None:
    """Zapisuje surowe dane binarne (np. PNG) do pliku."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def save_board_snapshot(image: bytes, board_type: Literal["current", "target"], tag: str) -> Path:
    """Zapisuje zrzut planszy PNG do output/boards i aktualizuje plik latest.

    Parametry:
    - `image`: bytes obrazu PNG pobranego z huba,
    - `board_type`: typ planszy (`current` albo `target`),
    - `tag`: krótki identyfikator etapu (np. `fetch`, `refresh`).

    Zwraca ścieżkę do zapisanego snapshotu.
    """

    boards_dir = OUTPUT_DIR / "boards"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = boards_dir / f"{ts}_{board_type}_{tag}.png"
    latest_path = boards_dir / f"latest_{board_type}.png"
    write_binary(snapshot_path, image)
    write_binary(latest_path, image)
    return snapshot_path


def preprocess_board_image_for_tiles(image: bytes, threshold: int) -> bytes:
    """Binaruje obraz: białe tło, czarne linie (grube i cienkie)."""

    try:
        from PIL import Image, ImageOps
    except Exception as error:  # noqa: BLE001
        raise RuntimeError("Brak biblioteki Pillow. Zainstaluj: pip install pillow") from error

    with Image.open(io.BytesIO(image)) as img:
        gray = img.convert("L")
        normalized = ImageOps.autocontrast(gray)
        bw = normalized.point(lambda p: 0 if p < threshold else 255, mode="L")
        # Delikatne domknięcie do czarno-białego zapisu RGB (czytelne dla dalszych kroków).
        out = bw.convert("RGB")
        buff = io.BytesIO()
        out.save(buff, format="PNG")
        return buff.getvalue()


def detect_table_bbox_with_vision(cfg: AppConfig, image: bytes) -> VisionTableBox:
    """Wykrywa bbox całej tabeli 3x3 tak, by ramka była w całości widoczna."""

    try:
        from PIL import Image
    except Exception as error:  # noqa: BLE001
        raise RuntimeError("Brak biblioteki Pillow. Zainstaluj: pip install pillow") from error

    with Image.open(io.BytesIO(image)) as img:
        width, height = img.size

    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)
    image_url = image_bytes_to_data_url(image)
    errors: list[str] = []

    for model_name in cfg.vision_models:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Znajdź CAŁĄ tabelę/szachownicę 3x3 i zwróć WYŁĄCZNIE JSON: "
                            "{\"left_pct\":...,\"top_pct\":...,\"right_pct\":...,\"bottom_pct\":...}. "
                            "Wartości jako procenty 0..1 względem całego obrazu. "
                            "BBox musi obejmować pełną zewnętrzną ramkę tabeli (górną, dolną, lewą, prawą). "
                            "Nie ucinaj górnej krawędzi."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": f"Rozmiar obrazu: width={width}, height={height}"},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    },
                ],
            )
            parsed = extract_first_json_object(completion.choices[0].message.content or "")
            box = VisionTableBox(
                left_pct=float(parsed.get("left_pct")),
                top_pct=float(parsed.get("top_pct")),
                right_pct=float(parsed.get("right_pct")),
                bottom_pct=float(parsed.get("bottom_pct")),
                model_name=model_name,
            )
            # lekki sanity check rozmiaru tabeli
            if (box.right_pct - box.left_pct) < 0.25 or (box.bottom_pct - box.top_pct) < 0.25:
                raise ValueError("Wykryta tabela jest podejrzanie mała.")
            return box
        except Exception as error:  # noqa: BLE001
            errors.append(f"{model_name}: {error}")

    raise RuntimeError("Nie udało się wykryć bbox tabeli przez vision. " + " | ".join(errors))


def table_box_pct_to_pixels(box: VisionTableBox, width: int, height: int) -> tuple[int, int, int, int]:
    """Przelicza bbox tabeli z procentów na piksele."""

    left = max(0, min(width - 1, int(round(box.left_pct * width))))
    top = max(0, min(height - 1, int(round(box.top_pct * height))))
    right = max(left + 1, min(width, int(round(box.right_pct * width))))
    bottom = max(top + 1, min(height, int(round(box.bottom_pct * height))))
    return left, top, right, bottom


def split_cropped_table_into_equal_tiles(
    table_image: Any,
    inset_ratio: float = 0.05,
) -> dict[str, Any]:
    """Dzieli obraz tabeli równo na 3x3 i zwraca mapę label -> tile Image."""

    width, height = table_image.size
    x_lines = [int(round(width * k / 3.0)) for k in range(4)]
    y_lines = [int(round(height * k / 3.0)) for k in range(4)]
    out: dict[str, Any] = {}
    for row in range(1, 4):
        for col in range(1, 4):
            x0, x1 = x_lines[col - 1], x_lines[col]
            y0, y1 = y_lines[row - 1], y_lines[row]
            tile = table_image.crop((x0, y0, x1, y1))
            if inset_ratio > 0:
                t_w, t_h = tile.size
                dx = int(round(t_w * inset_ratio))
                dy = int(round(t_h * inset_ratio))
                if t_w - 2 * dx > 4 and t_h - 2 * dy > 4:
                    tile = tile.crop((dx, dy, t_w - dx, t_h - dy))
            out[f"{row}x{col}"] = tile
    return out


def parse_tile_ports_with_model(
    cfg: AppConfig,
    model_name: str,
    tile_image_png: bytes,
) -> list[str]:
    """Odczytuje porty U/R/D/L z pojedynczego kafelka."""

    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)
    image_url = image_bytes_to_data_url(tile_image_png)
    completion = client.chat.completions.create(
        model=model_name,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "Dla pojedynczego kafelka zwróć WYŁĄCZNIE JSON: "
                    "{\"ports\":[\"U\",\"R\",...]} gdzie ports to podzbiór U/R/D/L."
                ),
            },
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": image_url}}],
            },
        ],
    )
    parsed = extract_first_json_object(completion.choices[0].message.content or "")
    ports = parsed.get("ports") or []
    if not isinstance(ports, list):
        raise ValueError("Brak listy ports w odpowiedzi modelu.")
    normalized = [str(p).strip().upper() for p in ports]
    normalized = [p for p in normalized if p in {"U", "R", "D", "L"}]
    return sorted(set(normalized), key=DIRECTION_ORDER.index)


def save_board_tiles(
    cfg: AppConfig,
    image: bytes,
    board_type: Literal["current", "target"],
    tag: str,
) -> tuple[Path, Path]:
    """Wycina siatkę 3x3 i zapisuje kafelki `row_col.png`.

    Zapisy:
    - `output/tiles/<timestamp>_<board_type>_<tag>/<row>_<col>.png`
    - `output/tiles/latest_<board_type>/<row>_<col>.png`
    Cięcie odbywa się wyłącznie na podstawie bboxów 9 pól zwróconych przez model vision.
    """

    try:
        from PIL import Image
    except Exception as error:  # noqa: BLE001
        raise RuntimeError("Brak biblioteki Pillow. Zainstaluj: pip install pillow") from error

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tiles_base_dir = OUTPUT_DIR / "tiles"
    run_dir = tiles_base_dir / f"{ts}_{board_type}_{tag}"
    latest_dir = tiles_base_dir / f"latest_{board_type}"
    run_dir.mkdir(parents=True, exist_ok=True)
    latest_dir.mkdir(parents=True, exist_ok=True)
    # Zapisz pełny pobrany obraz, żeby łatwo porównać z pociętymi kafelkami.
    write_binary(run_dir / "full.png", image)
    write_binary(latest_dir / "latest_full.png", image)
    # Preprocessing: wybiel tło i zostaw czarne linie.
    preprocessed = preprocess_board_image_for_tiles(
        image=image,
        threshold=cfg.tiles_binarize_threshold,
    )
    write_binary(run_dir / "preprocessed_full.png", preprocessed)
    write_binary(latest_dir / "latest_preprocessed_full.png", preprocessed)

    with Image.open(io.BytesIO(preprocessed)) as img:
        img = img.convert("RGB")
        # Krok 1: wykryj i wytnij całą tabelę z widoczną ramką.
        table_box = detect_table_bbox_with_vision(cfg, preprocessed)
        left, top, right, bottom = table_box_pct_to_pixels(table_box, img.size[0], img.size[1])
        log(
            "Detected table bbox via vision: "
            f"model={table_box.model_name}, left_pct={table_box.left_pct:.4f}, "
            f"top_pct={table_box.top_pct:.4f}, right_pct={table_box.right_pct:.4f}, "
            f"bottom_pct={table_box.bottom_pct:.4f}, px=({left},{top},{right},{bottom})"
        )
        write_json(
            run_dir / "table_bbox.json",
            {
                "model": table_box.model_name,
                "left_pct": table_box.left_pct,
                "top_pct": table_box.top_pct,
                "right_pct": table_box.right_pct,
                "bottom_pct": table_box.bottom_pct,
                "left_px": left,
                "top_px": top,
                "right_px": right,
                "bottom_px": bottom,
            },
        )
        detected_grid_crop = img.crop((left, top, right, bottom))
        detected_grid_crop.save(run_dir / "detected_grid_crop.png", format="PNG")
        detected_grid_crop.save(latest_dir / "latest_detected_grid_crop.png", format="PNG")

        # Krok 2: podziel lokalnie tabelę równo 3x3 i zapisz kafelki.
        tile_images = split_cropped_table_into_equal_tiles(detected_grid_crop, inset_ratio=0.05)
        for label, tile in tile_images.items():
            row, col = label.split("x")
            name = f"{row}_{col}.png"
            tile.save(run_dir / name, format="PNG")
            tile.save(latest_dir / name, format="PNG")

    return run_dir, latest_dir


def parse_vision_models(raw: str) -> list[str]:
    """Parsuje CSV modeli vision do listy fallbacków."""

    parsed = [p.strip() for p in raw.split(",") if p.strip()]
    return parsed if parsed else [DEFAULT_VISION_MODEL]


def build_config(dry_run: bool) -> AppConfig:
    """Buduje konfigurację z env + domyślnych wartości."""

    load_env_files()
    return AppConfig(
        hub_api_key=(os.getenv("HUB_API_KEY", "").strip() or os.getenv("API_KEY", "").strip()),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY", "").strip(),
        openrouter_base_url=(os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").strip()),
        verify_url=(os.getenv("VERIFY_URL", VERIFY_URL).strip() or VERIFY_URL),
        task_name=(os.getenv("ELECTRICITY_TASK_NAME", TASK_NAME).strip() or TASK_NAME),
        board_url_template=(
            os.getenv("ELECTRICITY_BOARD_URL_TEMPLATE", "").strip()
            or "https://hub.ag3nts.org/data/{apikey}/electricity.png"
        ),
        solved_board_url=(os.getenv("ELECTRICITY_SOLVED_URL", SOLVED_BOARD_URL).strip() or SOLVED_BOARD_URL),
        orchestrator_model=(
            os.getenv("ELECTRICITY_ORCHESTRATOR_MODEL", DEFAULT_ORCHESTRATOR_MODEL).strip()
            or DEFAULT_ORCHESTRATOR_MODEL
        ),
        vision_models=parse_vision_models(
            os.getenv("ELECTRICITY_VISION_MODELS", DEFAULT_VISION_MODELS_CSV)
        ),
        vision_reads_current=int(os.getenv("ELECTRICITY_VISION_READS_CURRENT", "2")),
        vision_reads_target=int(os.getenv("ELECTRICITY_VISION_READS_TARGET", "3")),
        vision_reads_repair=int(os.getenv("ELECTRICITY_VISION_READS_REPAIR", "3")),
        vision_target_audit_reads=int(os.getenv("ELECTRICITY_VISION_TARGET_AUDIT_READS", "6")),
        tiles_binarize_threshold=int(os.getenv("ELECTRICITY_TILES_BINARIZE_THRESHOLD", "190")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60")),
        max_agent_rounds=int(os.getenv("ELECTRICITY_MAX_ROUNDS", "16")),
        max_finalize_steps=int(os.getenv("ELECTRICITY_MAX_FINALIZE_STEPS", "8")),
        max_total_rotations=int(os.getenv("ELECTRICITY_MAX_ROTATIONS", "120")),
        default_batch_size=int(os.getenv("ELECTRICITY_BATCH_SIZE", "4")),
        allow_vision_fallback=(
            os.getenv("ELECTRICITY_ALLOW_VISION_FALLBACK", "false").strip().lower()
            in {"1", "true", "yes", "y", "on"}
        ),
        dry_run=dry_run,
    )


def build_board_url(cfg: AppConfig, reset: bool) -> str:
    """Buduje URL planszy bieżącej, opcjonalnie z `?reset=1`."""

    base = cfg.board_url_template.format(apikey=cfg.hub_api_key)
    if not reset:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}reset=1"


def fetch_binary(url: str, timeout_seconds: int, max_retries: int = 3) -> bytes:
    """Pobiera bytes z URL z retry/backoff dla odpowiedzi 429.

    Hub potrafi zwrócić 429 przy intensywnych pętlach. Wtedy czekamy
    (preferując nagłówek `Retry-After`) i ponawiamy próbę.
    """

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(url, timeout=timeout_seconds)
            if response.status_code == 429 and attempt < max_retries:
                retry_after = response.headers.get("Retry-After")
                wait_seconds = 2.0
                if retry_after:
                    try:
                        wait_seconds = max(1.0, float(retry_after))
                    except ValueError:
                        wait_seconds = 2.0
                else:
                    wait_seconds = float(attempt * 2)
                log(f"HTTP 429 for {url}; retry in {wait_seconds:.1f}s (attempt {attempt}/{max_retries})")
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            return response.content
        except Exception as error:  # noqa: BLE001
            last_error = error
            if attempt < max_retries:
                wait_seconds = float(attempt * 1.5)
                log(f"Fetch failed for {url}; retry in {wait_seconds:.1f}s (attempt {attempt}/{max_retries})")
                time.sleep(wait_seconds)
                continue
            break

    assert last_error is not None
    raise last_error


def image_bytes_to_data_url(image: bytes) -> str:
    """Konwertuje PNG bytes do data-url."""

    encoded = base64.b64encode(image).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def extract_first_json_object(text: str) -> dict[str, Any]:
    """Wyciąga pierwszy obiekt JSON z odpowiedzi modelu."""

    cleaned = text.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return json.loads(cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        raise ValueError("Model nie zwrócił obiektu JSON.")
    return json.loads(match.group(0))


def find_flag(payload: Any) -> str | None:
    """Szuka tokenu `{FLG:...}` w dowolnym payloadzie serializowalnym do JSON."""

    blob = json.dumps(payload, ensure_ascii=False)
    match = re.search(r"\{FLG:[^}]+\}", blob)
    return match.group(0) if match else None


def rotate_ports(ports: list[str], turns_right: int) -> list[str]:
    """Zwraca porty po N obrotach 90° w prawo."""

    result = sorted(set(ports), key=DIRECTION_ORDER.index)
    for _ in range(turns_right):
        result = sorted({ROTATE_RIGHT_MAP[p] for p in result}, key=DIRECTION_ORDER.index)
    return result


def compute_turns_to_match(current_ports: list[str], target_ports: list[str]) -> int:
    """Znajduje minimalną liczbę obrotów 0..3 dopasowując current do target."""

    target = sorted(set(target_ports), key=DIRECTION_ORDER.index)
    for turns in range(4):
        if rotate_ports(current_ports, turns) == target:
            return turns
    raise ValueError(f"Brak dopasowania przez rotacje: current={current_ports}, target={target_ports}")


def build_deterministic_plan(current: BoardState, target: BoardState) -> RotationPlan:
    """Wylicza plan obrotów przez porównanie portów 9 pól."""

    c_map = current.by_label()
    t_map = target.by_label()
    moves: list[PlannedMove] = []
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            turns = compute_turns_to_match(c_map[label].ports, t_map[label].ports)
            if turns:
                moves.append(
                    PlannedMove(
                        position=CellPosition(row=row, col=col),
                        turns_right=turns,
                        reason=f"{label}: {c_map[label].ports} -> {t_map[label].ports}",
                    )
                )
    return RotationPlan(
        strategy_summary="Plan deterministyczny na podstawie porównania portów U/R/D/L.",
        moves=moves,
    )


def board_ports_fingerprint(board: BoardState) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Tworzy stabilny fingerprint planszy po etykietach i portach."""

    by_label = board.by_label()
    items: list[tuple[str, tuple[str, ...]]] = []
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            items.append((label, tuple(by_label[label].ports)))
    return tuple(items)


def edge_consistency_score(board: BoardState) -> int:
    """Ocenia spójność sąsiadów: każde zgodne połączenie +1, niespójne -2."""

    by_label = board.by_label()
    score = 0
    for row in range(1, 4):
        for col in range(1, 3):
            left = by_label[f"{row}x{col}"]
            right = by_label[f"{row}x{col+1}"]
            if ("R" in left.ports) == ("L" in right.ports):
                score += 1
            else:
                score -= 2
    for row in range(1, 3):
        for col in range(1, 4):
            top = by_label[f"{row}x{col}"]
            bottom = by_label[f"{row+1}x{col}"]
            if ("D" in top.ports) == ("U" in bottom.ports):
                score += 1
            else:
                score -= 2
    return score


def build_consensus_board(source: Literal["current", "target"], boards: list[BoardState]) -> BoardState:
    """Buduje planszę konsensusową per kafelek (majority voting + tie-break)."""

    if not boards:
        raise ValueError("Brak plansz do konsensusu.")

    samples = [b.by_label() for b in boards]
    cells: list[BoardCell] = []
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            counts: dict[tuple[str, ...], int] = {}
            for sample in samples:
                key = tuple(sample[label].ports)
                counts[key] = counts.get(key, 0) + 1
            # majority; w remisie preferuj bogatszy kształt (więcej portów), potem porządek leksykalny
            best_ports = sorted(counts.items(), key=lambda x: (x[1], len(x[0]), x[0]), reverse=True)[0][0]
            cells.append(
                BoardCell(
                    position=CellPosition(row=row, col=col),
                    ports=list(best_ports),
                )
            )
    return BoardState(source=source, cells=cells)


def parse_board_consensus_with_model(
    cfg: AppConfig,
    image: bytes,
    source: Literal["current", "target"],
    model_name: str,
    reads: int,
) -> BoardState:
    """Wykonuje kilka odczytów tym samym modelem i składa planszę metodą voting."""

    parsed_boards: list[BoardState] = []
    errors: list[str] = []
    for idx in range(1, reads + 1):
        try:
            board = parse_board_with_specific_model(
                cfg=cfg,
                image=image,
                source=source,
                model_name=model_name,
            )
            parsed_boards.append(board)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{model_name}#{idx}: {error}")

    if not parsed_boards:
        raise RuntimeError("Brak poprawnych odczytów vision. " + " | ".join(errors))

    return build_consensus_board(source=source, boards=parsed_boards)


def parse_board_with_vision(cfg: AppConfig, image: bytes, source: Literal["current", "target"]) -> tuple[BoardState, str]:
    """Odczytuje planszę przez vision z fallbackiem między modelami."""

    reads = cfg.vision_reads_target if source == "target" else cfg.vision_reads_current
    errors: list[str] = []
    best_board: BoardState | None = None
    best_model = ""
    best_score = -10_000

    for model_name in cfg.vision_models:
        log(f"Vision parse ({source}) with model={model_name}, reads={reads}")
        try:
            board = parse_board_consensus_with_model(
                cfg=cfg,
                image=image,
                source=source,
                model_name=model_name,
                reads=reads,
            )
            score = edge_consistency_score(board)
            if score > best_score:
                best_score = score
                best_board = board
                best_model = model_name
            log(f"Vision parse ({source}) OK with model={model_name}, edge_score={score}")
        except Exception as error:  # noqa: BLE001
            errors.append(f"{model_name}: {error}")
            log(f"Vision parse ({source}) failed for model={model_name}")

    if best_board is None:
        raise RuntimeError("Vision fallback failed: " + " | ".join(errors))
    return best_board, best_model


def parse_board_with_specific_model(
    cfg: AppConfig,
    image: bytes,
    source: Literal["current", "target"],
    model_name: str,
) -> BoardState:
    """Parsuje planszę jednym modelem: bbox tabeli(%) + lokalny split + per-tile vision."""

    try:
        from PIL import Image
    except Exception as error:  # noqa: BLE001
        raise RuntimeError("Brak biblioteki Pillow. Zainstaluj: pip install pillow") from error

    preprocessed = preprocess_board_image_for_tiles(image=image, threshold=cfg.tiles_binarize_threshold)
    with Image.open(io.BytesIO(preprocessed)) as img:
        img = img.convert("RGB")
        width, height = img.size
        table_box = detect_table_bbox_with_vision(
            cfg.model_copy(update={"vision_models": [model_name]}),
            preprocessed,
        )
        left, top, right, bottom = table_box_pct_to_pixels(table_box, width, height)
        table_crop = img.crop((left, top, right, bottom))
        tile_images = split_cropped_table_into_equal_tiles(table_crop, inset_ratio=0.05)

        cells: list[BoardCell] = []
        tile_trace: list[dict[str, Any]] = []
        for row in range(1, 4):
            for col in range(1, 4):
                label = f"{row}x{col}"
                tile = tile_images[label]
                buff = io.BytesIO()
                tile.save(buff, format="PNG")
                ports = parse_tile_ports_with_model(cfg, model_name=model_name, tile_image_png=buff.getvalue())
                cells.append(
                    BoardCell(
                        position=CellPosition(row=row, col=col),
                        ports=ports,
                    )
                )
                tile_trace.append({"label": label, "ports": ports})

    append_jsonl(
        OUTPUT_DIR / "vision_parse_trace.jsonl",
        {
            "ts": now_iso(),
            "source": source,
            "model": model_name,
            "table_bbox_pct": {
                "left_pct": table_box.left_pct,
                "top_pct": table_box.top_pct,
                "right_pct": table_box.right_pct,
                "bottom_pct": table_box.bottom_pct,
            },
            "table_bbox_px": {"left": left, "top": top, "right": right, "bottom": bottom},
            "tiles": tile_trace,
        },
    )
    return BoardState(source=source, cells=cells)


def deterministic_compatibility_score(current: BoardState, target: BoardState) -> int:
    """Zlicza ile pól da się dopasować rotacją 0..3 (max=9)."""

    c_map = current.by_label()
    t_map = target.by_label()
    score = 0
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            try:
                compute_turns_to_match(c_map[label].ports, t_map[label].ports)
                score += 1
            except Exception:
                continue
    return score


def select_best_current_board_against_target(
    cfg: AppConfig,
    target: BoardState,
    current_image: bytes,
) -> tuple[BoardState, str, int]:
    """Wybiera najlepszy odczyt current względem target spośród modeli vision."""

    best_board: BoardState | None = None
    best_model = ""
    best_score = -1
    errors: list[str] = []

    for model_name in cfg.vision_models:
        try:
            candidate = parse_board_consensus_with_model(
                cfg=cfg,
                image=current_image,
                source="current",
                model_name=model_name,
                reads=cfg.vision_reads_repair,
            )
            score = deterministic_compatibility_score(candidate, target)
            if score > best_score:
                best_score = score
                best_board = candidate
                best_model = model_name
        except Exception as error:  # noqa: BLE001
            errors.append(f"{model_name}: {error}")

    if best_board is None:
        raise RuntimeError("Nie udało się odczytać current przez żaden model. " + " | ".join(errors))
    return best_board, best_model, best_score


def robust_reparse_current_and_target(
    cfg: AppConfig,
    current_image: bytes,
    target_image: bytes,
) -> tuple[BoardState, str, BoardState, str, int]:
    """Pełny remap obu plansz z wielokrotnym odczytem i oceną jakości."""

    best_target: BoardState | None = None
    best_target_model = ""
    best_target_score = -10_000
    target_errors: list[str] = []
    for model_name in cfg.vision_models:
        try:
            candidate = parse_board_consensus_with_model(
                cfg=cfg,
                image=target_image,
                source="target",
                model_name=model_name,
                reads=cfg.vision_reads_repair,
            )
            score = edge_consistency_score(candidate)
            if score > best_target_score:
                best_target_score = score
                best_target = candidate
                best_target_model = model_name
        except Exception as error:  # noqa: BLE001
            target_errors.append(f"{model_name}: {error}")
    if best_target is None:
        raise RuntimeError("Nie udało się zbudować target w trybie repair. " + " | ".join(target_errors))

    best_current: BoardState | None = None
    best_current_model = ""
    best_compat = -1
    best_current_edge = -10_000
    current_errors: list[str] = []
    for model_name in cfg.vision_models:
        try:
            candidate = parse_board_consensus_with_model(
                cfg=cfg,
                image=current_image,
                source="current",
                model_name=model_name,
                reads=cfg.vision_reads_repair,
            )
            compat = deterministic_compatibility_score(candidate, best_target)
            edge = edge_consistency_score(candidate)
            if (compat > best_compat) or (compat == best_compat and edge > best_current_edge):
                best_current = candidate
                best_current_model = model_name
                best_compat = compat
                best_current_edge = edge
        except Exception as error:  # noqa: BLE001
            current_errors.append(f"{model_name}: {error}")
    if best_current is None:
        raise RuntimeError("Nie udało się zbudować current w trybie repair. " + " | ".join(current_errors))

    return best_current, best_current_model, best_target, best_target_model, best_compat


def build_plan_with_vision_fallback(cfg: AppConfig, current_image: bytes, target_image: bytes) -> tuple[RotationPlan, str]:
    """Buduje plan obrotów bezpośrednio z dwóch obrazów (fallback).

    Używany, gdy odczyty portów current/target nie dają spójnego planu
    deterministycznego. Model zwraca listę ruchów, którą walidujemy Pydantic.
    """

    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)
    current_url = image_bytes_to_data_url(current_image)
    target_url = image_bytes_to_data_url(target_image)

    errors: list[str] = []
    for model_name in cfg.vision_models:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Porównaj obraz CURRENT z TARGET dla puzzle 3x3. "
                            "Zwróć WYŁĄCZNIE JSON: "
                            "{\"strategy_summary\":\"...\",\"moves\":[{\"row\":1,\"col\":1,\"turns_right\":1,\"reason\":\"...\"}]} "
                            "Analizuj każdy kwadrat osobno względem wzorca TARGET. "
                            "Jeśli kafelek jest już poprawnie ustawiony, nie dodawaj go do `moves`. "
                            "Ujmuj tylko pola wymagające obrotu i nie modyfikuj dalej pól już poprawnych."
                        ),
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "CURRENT"},
                            {"type": "image_url", "image_url": {"url": current_url}},
                            {"type": "text", "text": "TARGET"},
                            {"type": "image_url", "image_url": {"url": target_url}},
                        ],
                    },
                ],
            )

            parsed = extract_first_json_object(completion.choices[0].message.content or "")
            raw_moves = parsed.get("moves") or []
            moves: list[PlannedMove] = []
            for raw_move in raw_moves:
                vm = VisionPlannedMove.model_validate(raw_move)
                moves.append(
                    PlannedMove(
                        position=CellPosition(row=vm.row, col=vm.col),
                        turns_right=vm.turns_right,
                        reason=vm.reason,
                    )
                )
            plan = RotationPlan(
                strategy_summary=str(parsed.get("strategy_summary") or "Plan vision fallback."),
                moves=moves,
            )
            return plan, model_name
        except Exception as error:  # noqa: BLE001
            errors.append(f"{model_name}: {error}")

    raise RuntimeError("Vision plan fallback failed: " + " | ".join(errors))


def sanitize_vision_plan_with_known_boards(
    plan: RotationPlan,
    current: BoardState,
    target: BoardState,
) -> tuple[RotationPlan, int]:
    """Sanityzuje plan vision względem znanego current/target.

    Funkcja:
    - usuwa ruchy dla pól już poprawnych (`turns_right == 0`),
    - normalizuje turns_right do wartości deterministycznej, jeśli da się policzyć,
    - deduplikuje ruchy dla tej samej pozycji (ostatni wpis wygrywa).
    """

    c_map = current.by_label()
    t_map = target.by_label()
    normalized: dict[str, PlannedMove] = {}
    removed = 0

    for move in plan.moves:
        label = move.position.label()
        try:
            expected_turns = compute_turns_to_match(c_map[label].ports, t_map[label].ports)
            if expected_turns == 0:
                removed += 1
                continue
            normalized[label] = PlannedMove(
                position=move.position,
                turns_right=expected_turns,
                reason=(
                    f"{move.reason} | sanitized_expected_turns={expected_turns}"
                    if move.reason
                    else f"sanitized_expected_turns={expected_turns}"
                ),
            )
        except Exception:
            normalized[label] = move

    sanitized = RotationPlan(
        strategy_summary=plan.strategy_summary + " | sanitized_against_known_boards",
        moves=list(normalized.values()),
    )
    return sanitized, removed


def send_single_rotation(cfg: AppConfig, rotate_label: str, step_index: int) -> VerifyResponseRecord:
    """Wysyła pojedynczy obrót pola do `/verify`."""

    payload = VerifyPayload(
        apikey=cfg.hub_api_key,
        task=cfg.task_name,
        answer=RotationAnswer(rotate=rotate_label),
    )
    response = requests.post(cfg.verify_url, json=payload.model_dump(), timeout=cfg.request_timeout_seconds)
    try:
        body: Any = response.json()
    except Exception:
        body = {"raw_text": response.text}
    return VerifyResponseRecord(
        ts=now_iso(),
        step=f"ROTATE_{step_index}_{rotate_label}",
        request_body=payload.model_dump(),
        status_code=response.status_code,
        response_body=body,
    )


def tool_specs() -> list[dict[str, Any]]:
    """Definicje narzędzi dla pętli function-calling."""

    return [
        {
            "type": "function",
            "function": {
                "name": "fetch_current_board",
                "description": "Pobiera i parsuje planszę bieżącą. Ustaw reset=true tylko na start.",
                "parameters": {"type": "object", "properties": {"reset": {"type": "boolean", "default": False}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "fetch_target_board",
                "description": "Pobiera i parsuje planszę docelową.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "build_rotation_plan",
                "description": "Buduje plan current->target i kolejkę rotacji.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "execute_rotation_batch",
                "description": "Wykonuje partię obrotów i odświeża current board po batchu.",
                "parameters": {"type": "object", "properties": {"batch_size": {"type": "integer", "minimum": 1, "maximum": 30}}},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "get_runtime_status",
                "description": "Zwraca status kolejki, liczbę obrotów i flagę.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def dispatch_tool_call(
    cfg: AppConfig,
    state: RuntimeState,
    tool_name: str,
    arguments: dict[str, Any],
    verify_trace_path: Path,
    tool_trace_path: Path,
) -> ToolCallResult:
    """Mapuje tool call na lokalną implementację."""

    log(f"Tool call: {tool_name} args={arguments}")

    if tool_name == "fetch_current_board":
        reset = bool(arguments.get("reset", False))
        image = fetch_binary(build_board_url(cfg, reset=reset), cfg.request_timeout_seconds)
        state.last_current_image = image
        snapshot_path = save_board_snapshot(image, "current", "fetch")
        try:
            run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, image, "current", "fetch")
            log(f"Saved current tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
        except Exception as tiles_error:  # noqa: BLE001
            log(f"Warning: failed to save current tiles: {tiles_error}")
        board, model_name = parse_board_with_vision(cfg, image, source="current")
        state.current_board = board
        append_jsonl(
            tool_trace_path,
            {
                "ts": now_iso(),
                "tool": tool_name,
                "reset": reset,
                "vision_model": model_name,
                "snapshot_path": str(snapshot_path),
                "cells": [c.model_dump() for c in board.cells],
            },
        )
        log(f"Saved current board snapshot: {snapshot_path}")
        return ToolCallResult(ok=True, tool_name=tool_name, data={"vision_model": model_name, "cell_count": len(board.cells)})

    if tool_name == "fetch_target_board":
        image = fetch_binary(cfg.solved_board_url, cfg.request_timeout_seconds)
        state.last_target_image = image
        snapshot_path = save_board_snapshot(image, "target", "fetch")
        try:
            run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, image, "target", "fetch")
            log(f"Saved target tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
        except Exception as tiles_error:  # noqa: BLE001
            log(f"Warning: failed to save target tiles: {tiles_error}")
        board, model_name = parse_board_with_vision(cfg, image, source="target")
        state.target_board = board
        append_jsonl(
            tool_trace_path,
            {
                "ts": now_iso(),
                "tool": tool_name,
                "vision_model": model_name,
                "snapshot_path": str(snapshot_path),
                "cells": [c.model_dump() for c in board.cells],
            },
        )
        log(f"Saved target board snapshot: {snapshot_path}")
        return ToolCallResult(ok=True, tool_name=tool_name, data={"vision_model": model_name, "cell_count": len(board.cells)})

    if tool_name == "build_rotation_plan":
        if not state.current_board or not state.target_board:
            return ToolCallResult(ok=False, tool_name=tool_name, error="Brak current_board lub target_board.")
        compatibility_score: int | None = None
        if state.force_full_remap:
            try:
                log("build_rotation_plan: force_full_remap=True, remapping current+target")
                current_image = state.last_current_image or fetch_binary(
                    build_board_url(cfg, reset=False),
                    cfg.request_timeout_seconds,
                )
                target_image = state.last_target_image or fetch_binary(
                    cfg.solved_board_url,
                    cfg.request_timeout_seconds,
                )
                state.last_current_image = current_image
                state.last_target_image = target_image
                (
                    remapped_current,
                    remapped_current_model,
                    remapped_target,
                    remapped_target_model,
                    remapped_compat,
                ) = robust_reparse_current_and_target(
                    cfg=cfg,
                    current_image=current_image,
                    target_image=target_image,
                )
                state.current_board = remapped_current
                state.target_board = remapped_target
                compatibility_score = remapped_compat
                state.force_full_remap = False
                log(
                    "Remap done: "
                    f"current_model={remapped_current_model}, target_model={remapped_target_model}, "
                    f"compatibility={remapped_compat}/9"
                )
            except Exception as remap_error:  # noqa: BLE001
                state.force_full_remap = False
                return ToolCallResult(
                    ok=False,
                    tool_name=tool_name,
                    error=f"Nie udał się pełny remap current+target: {remap_error}",
                )
        try:
            state.current_plan = build_deterministic_plan(state.current_board, state.target_board)
            planning_mode = "deterministic_ports"
            if compatibility_score is None:
                compatibility_score = 9
            log("Plan built using deterministic ports mode")
        except Exception as error:  # noqa: BLE001
            # 1) Najpierw próbujemy poprawić odczyt current, wybierając model dający
            # najlepszą zgodność deterministyczną z target.
            try:
                current_image = state.last_current_image or fetch_binary(
                    build_board_url(cfg, reset=False),
                    cfg.request_timeout_seconds,
                )
                target_image = state.last_target_image or fetch_binary(
                    cfg.solved_board_url,
                    cfg.request_timeout_seconds,
                )
                state.last_current_image = current_image
                state.last_target_image = target_image

                repaired_current, repaired_model, repaired_score = select_best_current_board_against_target(
                    cfg=cfg,
                    target=state.target_board,
                    current_image=current_image,
                )
                state.current_board = repaired_current
                log(
                    "Re-read current for deterministic plan: "
                    f"model={repaired_model}, compatibility={repaired_score}/9"
                )
                compatibility_score = repaired_score
                state.current_plan = build_deterministic_plan(state.current_board, state.target_board)
                planning_mode = f"deterministic_ports_repaired:{repaired_model}"
                log(f"Plan built using {planning_mode}")
            except Exception as repaired_error:  # noqa: BLE001
                # 2) Opcjonalny fallback vision-plan (domyślnie wyłączony, bo bywa niestabilny).
                if not cfg.allow_vision_fallback:
                    return ToolCallResult(
                        ok=False,
                        tool_name=tool_name,
                        error=(
                            "Deterministyczny plan nie powiódł się nawet po naprawie odczytu current. "
                            f"original={error} | repaired={repaired_error}. "
                            "Użyj ponownie fetch_current_board/build_rotation_plan lub ustaw "
                            "ELECTRICITY_ALLOW_VISION_FALLBACK=true, jeśli chcesz dopuścić vision fallback."
                        ),
                    )

                try:
                    current_image = state.last_current_image or fetch_binary(
                        build_board_url(cfg, reset=False),
                        cfg.request_timeout_seconds,
                    )
                    target_image = state.last_target_image or fetch_binary(
                        cfg.solved_board_url,
                        cfg.request_timeout_seconds,
                    )
                    state.current_plan, fallback_model = build_plan_with_vision_fallback(
                        cfg, current_image=current_image, target_image=target_image
                    )
                    if state.current_board is not None and state.target_board is not None:
                        if compatibility_score is None:
                            compatibility_score = deterministic_compatibility_score(
                                state.current_board, state.target_board
                            )
                        state.current_plan, removed_moves = sanitize_vision_plan_with_known_boards(
                            plan=state.current_plan,
                            current=state.current_board,
                            target=state.target_board,
                        )
                        if removed_moves > 0:
                            log(f"Vision fallback sanitized: removed {removed_moves} already-correct move(s)")
                    planning_mode = f"vision_fallback:{fallback_model}"
                    log(f"Plan built using {planning_mode}")
                except Exception as fallback_error:  # noqa: BLE001
                    return ToolCallResult(
                        ok=False,
                        tool_name=tool_name,
                        error=(
                            "Nie udało się zbudować planu deterministycznie ani fallbackiem vision. "
                            f"original={error} | repaired={repaired_error} | fallback={fallback_error}"
                        ),
                    )
        state.pending_rotations = state.current_plan.expanded_rotation_labels()
        # Zabezpieczenie anty-loop: pusty plan przy niepełnej zgodności oznacza niestabilny odczyt.
        if not state.pending_rotations and state.current_board is not None and state.target_board is not None:
            score = compatibility_score
            if score is None:
                score = deterministic_compatibility_score(state.current_board, state.target_board)
            if score < 9:
                return ToolCallResult(
                    ok=False,
                    tool_name=tool_name,
                    error=(
                        f"Pusty plan przy niepełnej zgodności ({score}/9). "
                        "Wymagane odświeżenie planszy current i ponowne planowanie."
                    ),
                )
        append_jsonl(
            tool_trace_path,
            {
                "ts": now_iso(),
                "tool": tool_name,
                "plan": state.current_plan.model_dump(),
                "pending_rotations": state.pending_rotations,
                "planning_mode": planning_mode,
                "compatibility_score": compatibility_score,
            },
        )
        return ToolCallResult(
            ok=True,
            tool_name=tool_name,
            data={
                "pending_rotations": len(state.pending_rotations),
                "planning_mode": planning_mode,
                "compatibility_score": compatibility_score,
            },
        )

    if tool_name == "execute_rotation_batch":
        if not state.pending_rotations:
            return ToolCallResult(ok=False, tool_name=tool_name, error="Kolejka rotacji jest pusta.")
        batch_size = int(arguments.get("batch_size") or cfg.default_batch_size)
        labels = state.pending_rotations[: max(1, batch_size)]
        log(f"Executing rotation batch: size={len(labels)} labels={labels}")
        if state.total_rotations_sent + len(labels) > cfg.max_total_rotations:
            return ToolCallResult(ok=False, tool_name=tool_name, error="Przekroczono limit obrotów.")

        feedback: list[str] = []
        before_fingerprint = board_ports_fingerprint(state.current_board) if state.current_board else None
        if cfg.dry_run:
            state.pending_rotations = state.pending_rotations[len(labels) :]
            feedback.append(f"DRY_RUN labels={labels}")
        else:
            for label in labels:
                rec = send_single_rotation(cfg, label, state.total_rotations_sent + 1)
                append_jsonl(verify_trace_path, rec.model_dump())
                state.total_rotations_sent += 1
                state.pending_rotations = state.pending_rotations[1:]
                feedback.append(f"{rec.step}:{rec.status_code}")
                log(f"Sent rotate={label} status={rec.status_code}")
                flag = find_flag(rec.response_body)
                if flag:
                    state.flag = flag
                    log(f"FLAG found: {flag}")
                    break
                if rec.status_code >= 400:
                    break

        # Weryfikacja po partii: odświeżamy current board.
        try:
            refreshed = fetch_binary(build_board_url(cfg, reset=False), cfg.request_timeout_seconds)
            state.last_current_image = refreshed
            snapshot_path = save_board_snapshot(refreshed, "current", "refresh")
            try:
                run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, refreshed, "current", "refresh")
                log(f"Saved refreshed current tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
            except Exception as tiles_error:  # noqa: BLE001
                log(f"Warning: failed to save refreshed current tiles: {tiles_error}")
            board, model_name = parse_board_with_vision(cfg, refreshed, source="current")
            state.current_board = board
            feedback.append(f"refresh_ok:{model_name}")
            log(f"Saved refreshed current board snapshot: {snapshot_path}")
            after_fingerprint = board_ports_fingerprint(board)
            if labels and before_fingerprint is not None and after_fingerprint == before_fingerprint:
                state.no_progress_rotation_rounds += 1
                state.force_full_remap = True
                feedback.append("no_progress_detected:force_full_remap")
                log(
                    "No progress after rotation batch; "
                    f"no_progress_rotation_rounds={state.no_progress_rotation_rounds}. "
                    "Will force remap on next planning."
                )
            else:
                state.no_progress_rotation_rounds = 0
        except Exception as error:  # noqa: BLE001
            feedback.append(f"refresh_error:{error}")

        state.last_feedback = " | ".join(feedback)
        append_jsonl(
            tool_trace_path,
            {
                "ts": now_iso(),
                "tool": tool_name,
                "labels": labels,
                "dry_run": cfg.dry_run,
                "pending_after": len(state.pending_rotations),
                "total_rotations_sent": state.total_rotations_sent,
                "flag": state.flag,
                "feedback": state.last_feedback,
            },
        )
        return ToolCallResult(
            ok=True,
            tool_name=tool_name,
            data={
                "executed": labels,
                "pending_after": len(state.pending_rotations),
                "flag": state.flag,
                "feedback": state.last_feedback,
            },
        )

    if tool_name == "get_runtime_status":
        return ToolCallResult(
            ok=True,
            tool_name=tool_name,
            data={
                "has_current_board": state.current_board is not None,
                "has_target_board": state.target_board is not None,
                "has_plan": state.current_plan is not None,
                "pending_rotations": len(state.pending_rotations),
                "total_rotations_sent": state.total_rotations_sent,
                "flag": state.flag,
                "last_feedback": state.last_feedback,
            },
        )

    return ToolCallResult(ok=False, tool_name=tool_name, error="Nieznane narzędzie.")


def forced_progress_step(
    cfg: AppConfig,
    state: RuntimeState,
    verify_trace_path: Path,
    tool_trace_path: Path,
) -> ToolCallResult:
    """Wykonuje jeden deterministyczny krok postępu, gdy orchestrator milczy.

    Kolejność:
    1. Jeśli brak `target_board`, pobierz target.
    2. Jeśli brak `current_board`, pobierz current bez resetu.
    3. Jeśli brak kolejki ruchów, zbuduj plan.
    4. Jeśli są ruchy oczekujące, wykonaj jedną partię.

    Dzięki temu agent nie kończy pracy tylko dlatego, że model zwrócił
    tekst zamiast kolejnego function call.
    """

    if state.target_board is None:
        return dispatch_tool_call(
            cfg, state, "fetch_target_board", {}, verify_trace_path, tool_trace_path
        )
    if state.current_board is None:
        return dispatch_tool_call(
            cfg, state, "fetch_current_board", {"reset": False}, verify_trace_path, tool_trace_path
        )
    if not state.pending_rotations:
        build_result = dispatch_tool_call(
            cfg, state, "build_rotation_plan", {}, verify_trace_path, tool_trace_path
        )
        if build_result.ok:
            return build_result
        if build_result.error and (
            "Nie udało się zbudować planu deterministycznie" in build_result.error
            or "Brak dopasowania przez rotacje" in build_result.error
        ):
            state.force_full_remap = True
            log("Forced step: planning mismatch detected, force_full_remap=True")
        if build_result.error and "Pusty plan przy niepełnej zgodności" in build_result.error:
            log("Forced step: empty unstable plan detected, refreshing current and retrying plan build")
            refresh_result = dispatch_tool_call(
                cfg, state, "fetch_current_board", {"reset": False}, verify_trace_path, tool_trace_path
            )
            if not refresh_result.ok:
                return refresh_result
            retry_result = dispatch_tool_call(
                cfg, state, "build_rotation_plan", {}, verify_trace_path, tool_trace_path
            )
            return retry_result
        return build_result
    return dispatch_tool_call(
        cfg,
        state,
        "execute_rotation_batch",
        {"batch_size": cfg.default_batch_size},
        verify_trace_path,
        tool_trace_path,
    )


def finalize_after_max_rounds(
    cfg: AppConfig,
    state: RuntimeState,
    verify_trace_path: Path,
    tool_trace_path: Path,
    warnings: list[str],
) -> bool:
    """Dogrywka po limicie rund LLM: lokalne kroki postępu bez kolejnych wywołań modelu."""

    if cfg.max_finalize_steps <= 0:
        return False

    log(f"Start finalize phase: max_steps={cfg.max_finalize_steps}")
    for step_idx in range(1, cfg.max_finalize_steps + 1):
        if state.flag:
            return True
        if state.total_rotations_sent >= cfg.max_total_rotations:
            warnings.append("Osiągnięto globalny limit obrotów podczas fazy finalizacji.")
            return False

        result = forced_progress_step(cfg, state, verify_trace_path, tool_trace_path)
        log(f"Finalize step {step_idx}/{cfg.max_finalize_steps}: ok={result.ok}")
        if not result.ok:
            warnings.append(f"finalize_step_{step_idx}: {result.error}")
        if state.flag:
            return True

        # Jeśli nic nie ma do wykonania, nie ma sensu mielić kolejnych kroków.
        if not state.pending_rotations and state.current_plan is not None:
            break

    return state.flag is not None


def solve_with_function_calling(cfg: AppConfig, reset_first: bool) -> SolveResult:
    """Uruchamia agenta function-calling i prowadzi go do rozwiązania lub stopu."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    verify_trace_path = OUTPUT_DIR / "verify_trace.jsonl"
    tool_trace_path = OUTPUT_DIR / "tool_trace.jsonl"
    llm_trace_path = OUTPUT_DIR / "llm_trace.jsonl"

    state = RuntimeState()
    client = OpenAI(api_key=cfg.openrouter_api_key, base_url=cfg.openrouter_base_url)

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "Rozwiązujesz electricity wyłącznie przez function calling. "
                "Najpierw pobierz target/current (na starcie reset jeśli użytkownik oczekuje), "
                "zbuduj plan, wykonuj batchami i sprawdzaj status po każdej partii."
            ),
        },
        {
            "role": "user",
            "content": f"Rozwiąż zadanie. dry_run={cfg.dry_run}, reset_first={reset_first}.",
        },
    ]

    warnings: list[str] = []
    first_current_fetch_done = False
    log(
        "Start solve_with_function_calling "
        f"(dry_run={cfg.dry_run}, model={cfg.orchestrator_model}, vision={cfg.vision_models}, "
        f"reads_current={cfg.vision_reads_current}, reads_target={cfg.vision_reads_target}, "
        f"reads_repair={cfg.vision_reads_repair})"
    )

    for round_idx in range(1, cfg.max_agent_rounds + 1):
        log(f"Round {round_idx}/{cfg.max_agent_rounds}")
        completion = client.chat.completions.create(
            model=cfg.orchestrator_model,
            temperature=0,
            messages=messages,
            tools=tool_specs(),
            tool_choice="auto",
        )
        assistant = completion.choices[0].message
        append_jsonl(llm_trace_path, {"ts": now_iso(), "round": round_idx, "assistant": assistant.model_dump(exclude_none=True)})

        tool_calls = assistant.tool_calls or []
        if not tool_calls:
            log("No tool calls from orchestrator; running forced progress step")
            messages.append({"role": "assistant", "content": assistant.content or ""})
            forced = forced_progress_step(cfg, state, verify_trace_path, tool_trace_path)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "AUTOPILOT_PROGRESS_STEP_RESULT: "
                        + json.dumps(forced.model_dump(), ensure_ascii=False)
                    ),
                }
            )
            if not forced.ok:
                warnings.append(f"forced_progress_step: {forced.error}")
                log(f"Forced step failed: {forced.error}")
            if state.flag:
                return SolveResult(
                    ok=True,
                    dry_run=cfg.dry_run,
                    flag=state.flag,
                    total_rotations_sent=state.total_rotations_sent,
                    tool_rounds_used=round_idx,
                    warnings=warnings,
                )
            continue

        log(f"Orchestrator requested {len(tool_calls)} tool call(s)")
        assistant_payload: dict[str, Any] = {"role": "assistant", "tool_calls": [tc.model_dump(exclude_none=True) for tc in tool_calls]}
        if assistant.content:
            assistant_payload["content"] = assistant.content
        messages.append(assistant_payload)

        for tool_call in tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}

            if tool_name == "fetch_current_board" and reset_first and not first_current_fetch_done:
                arguments = {**arguments, "reset": True}
                first_current_fetch_done = True

            result = dispatch_tool_call(cfg, state, tool_name, arguments, verify_trace_path, tool_trace_path)
            log(f"Tool result: {tool_name} ok={result.ok}")
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result.model_dump(), ensure_ascii=False),
                }
            )

            if not result.ok:
                warnings.append(f"{tool_name}: {result.error}")

            if state.flag:
                return SolveResult(
                    ok=True,
                    dry_run=cfg.dry_run,
                    flag=state.flag,
                    total_rotations_sent=state.total_rotations_sent,
                    tool_rounds_used=round_idx,
                    warnings=warnings,
                )

            if state.total_rotations_sent >= cfg.max_total_rotations:
                warnings.append("Osiągnięto globalny limit obrotów.")
                return SolveResult(
                    ok=False,
                    dry_run=cfg.dry_run,
                    total_rotations_sent=state.total_rotations_sent,
                    tool_rounds_used=round_idx,
                    warnings=warnings,
                )

        if cfg.dry_run and state.current_plan is not None:
            warnings.append("Tryb dry-run: zakończono po zbudowaniu planu i pierwszym batchu.")
            return SolveResult(
                ok=True,
                dry_run=True,
                total_rotations_sent=0,
                tool_rounds_used=round_idx,
                warnings=warnings,
            )
    warnings.append("Wyczerpano limit rund function-calling.")
    solved_in_finalize = finalize_after_max_rounds(
        cfg=cfg,
        state=state,
        verify_trace_path=verify_trace_path,
        tool_trace_path=tool_trace_path,
        warnings=warnings,
    )
    if solved_in_finalize and state.flag:
        log("Solved in finalize phase after max rounds")
        return SolveResult(
            ok=True,
            dry_run=cfg.dry_run,
            flag=state.flag,
            total_rotations_sent=state.total_rotations_sent,
            tool_rounds_used=cfg.max_agent_rounds,
            warnings=warnings,
        )

    # Po osiągnięciu limitu rund pokaż aktualny odczyt planszy w notacji AxB ["U","R"].
    latest_board = state.current_board
    if latest_board is None:
        try:
            current_image = fetch_binary(build_board_url(cfg, reset=False), cfg.request_timeout_seconds)
            state.last_current_image = current_image
            latest_board, _ = parse_board_with_vision(cfg, current_image, source="current")
        except Exception as error:  # noqa: BLE001
            warnings.append(f"print_current_board_after_limit: {error}")
    if latest_board is not None:
        print("\n=== AKTUALNY UKŁAD PO LIMICIE RUND ===")
        for line in _format_board_ports_lines(latest_board):
            print(line)

    log("Stop: max rounds reached without flag")
    return SolveResult(
        ok=False,
        dry_run=cfg.dry_run,
        total_rotations_sent=state.total_rotations_sent,
        tool_rounds_used=cfg.max_agent_rounds,
        warnings=warnings,
    )


def _format_board_ports_lines(board: BoardState) -> list[str]:
    """Formatuje planszę do listy linii `AxB [\"U\",\"R\",...]`."""

    board_map = board.by_label()
    lines: list[str] = []
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            ports_json = json.dumps(board_map[label].ports, ensure_ascii=False)
            lines.append(f"{label} {ports_json}")
    return lines


def run_target_confidence_audit(cfg: AppConfig) -> None:
    """Audyt pewności odczytu TARGET: wielokrotne odczyty i raport niepewnych kafelków."""

    log(
        "Target confidence audit: "
        f"models={cfg.vision_models}, reads_per_model={cfg.vision_target_audit_reads}"
    )
    target_image = fetch_binary(cfg.solved_board_url, cfg.request_timeout_seconds)
    target_snapshot = save_board_snapshot(target_image, "target", "audit")
    try:
        run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, target_image, "target", "audit")
        log(f"Saved audit target tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
    except Exception as tiles_error:  # noqa: BLE001
        log(f"Warning: failed to save audit target tiles: {tiles_error}")

    samples: list[BoardState] = []
    errors: list[str] = []
    for model_name in cfg.vision_models:
        for idx in range(1, cfg.vision_target_audit_reads + 1):
            try:
                board = parse_board_with_specific_model(
                    cfg=cfg,
                    image=target_image,
                    source="target",
                    model_name=model_name,
                )
                samples.append(board)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{model_name}#{idx}: {error}")

    if not samples:
        print("\n=== TARGET AUDIT ===")
        print("Brak poprawnych odczytów TARGET.")
        if errors:
            print("Błędy:")
            for item in errors:
                print(f"- {item}")
        return

    total_samples = len(samples)
    per_label_counts: dict[str, dict[tuple[str, ...], int]] = {
        f"{r}x{c}": {} for r in range(1, 4) for c in range(1, 4)
    }
    for board in samples:
        by_label = board.by_label()
        for label, counters in per_label_counts.items():
            key = tuple(by_label[label].ports)
            counters[key] = counters.get(key, 0) + 1

    print("\n=== TARGET AUDIT ===")
    print(f"snapshot: {target_snapshot}")
    print(f"samples_ok: {total_samples}")
    print(f"samples_failed: {len(errors)}")
    if errors:
        print("sample_errors:")
        for item in errors:
            print(f"- {item}")

    print("\n=== TARGET CONSENSUS ===")
    uncertain_labels: list[str] = []
    for row in range(1, 4):
        for col in range(1, 4):
            label = f"{row}x{col}"
            counters = per_label_counts[label]
            ranked = sorted(counters.items(), key=lambda x: x[1], reverse=True)
            best_ports, best_count = ranked[0]
            confidence = best_count / total_samples
            ports_json = json.dumps(list(best_ports), ensure_ascii=False)
            print(f"{label} {ports_json} confidence={confidence:.2f} votes={best_count}/{total_samples}")
            if confidence < 0.8:
                uncertain_labels.append(label)

    print("\n=== TARGET UNCERTAIN TILES (<0.80) ===")
    if not uncertain_labels:
        print("Brak.")
        return

    for label in uncertain_labels:
        counters = per_label_counts[label]
        ranked = sorted(counters.items(), key=lambda x: x[1], reverse=True)
        variants = ", ".join(
            [f"{json.dumps(list(ports), ensure_ascii=False)}:{count}/{total_samples}" for ports, count in ranked]
        )
        print(f"{label} variants={variants}")


def run_export_tiles_only(cfg: AppConfig, reset_first: bool) -> None:
    """Tryb narzędziowy: tylko eksport kafelków 3x3 do plików PNG."""

    log(f"Export tiles only mode: reset_first={reset_first}")

    current_image = fetch_binary(build_board_url(cfg, reset=reset_first), cfg.request_timeout_seconds)
    current_snapshot = save_board_snapshot(current_image, "current", "tiles_only")
    current_run_dir, current_latest_dir = save_board_tiles(cfg, current_image, "current", "tiles_only")

    target_image = fetch_binary(cfg.solved_board_url, cfg.request_timeout_seconds)
    target_snapshot = save_board_snapshot(target_image, "target", "tiles_only")
    target_run_dir, target_latest_dir = save_board_tiles(cfg, target_image, "target", "tiles_only")

    print("\n=== EXPORT TILES ONLY ===")
    print(f"current_snapshot: {current_snapshot}")
    print(f"current_tiles_run: {current_run_dir}")
    print(f"current_tiles_latest: {current_latest_dir}")
    print(f"target_snapshot: {target_snapshot}")
    print(f"target_tiles_run: {target_run_dir}")
    print(f"target_tiles_latest: {target_latest_dir}")
    print("Zapisane pliki: 1_1.png ... 3_3.png")
    print("Tryb cięcia: vision-grid (linie tabeli wykryte przez model).")


def run_vision_inspection(cfg: AppConfig, reset_first: bool) -> None:
    """Tryb testowy: odczyt current/target przez vision i wypisanie adnotacji."""

    log("Vision inspection mode: fetch current and target, parse, print annotations.")

    current_image = fetch_binary(build_board_url(cfg, reset=reset_first), cfg.request_timeout_seconds)
    current_snapshot = save_board_snapshot(current_image, "current", "inspect")
    try:
        run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, current_image, "current", "inspect")
        log(f"Saved inspect current tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
    except Exception as tiles_error:  # noqa: BLE001
        log(f"Warning: failed to save inspect current tiles: {tiles_error}")
    current_board, current_model = parse_board_with_vision(cfg, current_image, source="current")

    target_image = fetch_binary(cfg.solved_board_url, cfg.request_timeout_seconds)
    target_snapshot = save_board_snapshot(target_image, "target", "inspect")
    try:
        run_tiles_dir, latest_tiles_dir = save_board_tiles(cfg, target_image, "target", "inspect")
        log(f"Saved inspect target tiles: run={run_tiles_dir} latest={latest_tiles_dir}")
    except Exception as tiles_error:  # noqa: BLE001
        log(f"Warning: failed to save inspect target tiles: {tiles_error}")
    target_board, target_model = parse_board_with_vision(cfg, target_image, source="target")

    print("\n=== CURRENT ===")
    print(f"model: {current_model}")
    print(f"snapshot: {current_snapshot}")
    for line in _format_board_ports_lines(current_board):
        print(line)

    print("\n=== TARGET ===")
    print(f"model: {target_model}")
    print(f"snapshot: {target_snapshot}")
    for line in _format_board_ports_lines(target_board):
        print(line)


def parse_args() -> argparse.Namespace:
    """Parsuje argumenty CLI."""

    parser = argparse.ArgumentParser(description="Agent electricity z function calling + pydantic.")
    parser.add_argument("--execute", action="store_true", help="Włącza realne wysyłanie obrotów.")
    parser.add_argument("--reset-first", action="store_true", help="Reset planszy na starcie.")
    parser.add_argument("--max-steps", type=int, default=None, help="Nadpisuje limit obrotów.")
    parser.add_argument(
        "--inspect-vision",
        action="store_true",
        help=(
            "Tryb testowy: pobiera current/target PNG, parsuje przez vision i wypisuje "
            "adnotacje AxB [\"U\",\"R\",...], bez wykonywania obrotów."
        ),
    )
    parser.add_argument(
        "--audit-target-confidence",
        action="store_true",
        help=(
            "Audyt wzorca TARGET: wielokrotnie odczytuje target PNG i wypisuje "
            "confidence per kafelek oraz listę niepewnych pól."
        ),
    )
    parser.add_argument(
        "--export-tiles-only",
        action="store_true",
        help=(
            "Pobiera current/target PNG i zapisuje kafelki 3x3 do osobnych plików "
            "(1_1.png ... 3_3.png), bez uruchamiania solvera."
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Punkt wejścia programu: konfiguracja, solve, zapis raportów."""

    args = parse_args()
    cfg = build_config(dry_run=not args.execute)
    cfg = cfg.model_copy(update={"max_agent_rounds": min(cfg.max_agent_rounds, FORCED_MAX_AGENT_ROUNDS)})
    if args.max_steps is not None:
        cfg = cfg.model_copy(update={"max_total_rotations": args.max_steps})

    if args.inspect_vision:
        run_vision_inspection(cfg=cfg, reset_first=args.reset_first)
        return
    if args.audit_target_confidence:
        run_target_confidence_audit(cfg=cfg)
        return
    if args.export_tiles_only:
        run_export_tiles_only(cfg=cfg, reset_first=args.reset_first)
        return

    write_json(
        OUTPUT_DIR / "run_meta.json",
        {
            "ts": now_iso(),
            "dry_run": cfg.dry_run,
            "orchestrator_model": cfg.orchestrator_model,
            "vision_models": cfg.vision_models,
            "vision_reads_current": cfg.vision_reads_current,
            "vision_reads_target": cfg.vision_reads_target,
            "vision_reads_repair": cfg.vision_reads_repair,
            "tiles_binarize_threshold": cfg.tiles_binarize_threshold,
            "verify_url": cfg.verify_url,
            "task_name": cfg.task_name,
        },
    )

    result = solve_with_function_calling(cfg, reset_first=args.reset_first)
    write_json(OUTPUT_DIR / "result.json", result.model_dump())
    print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

