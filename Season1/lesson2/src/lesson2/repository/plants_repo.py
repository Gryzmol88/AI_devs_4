import json
from pathlib import Path

from ..models import PowerPlant


def save_plants(path: Path, plants: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plants, ensure_ascii=False, indent=2), encoding="utf-8")


def load_plants(path: Path) -> list[PowerPlant]:
    if not path.exists():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw if isinstance(raw, list) else raw.get("items", [])
    out: list[PowerPlant] = []

    for item in items:
        code = item.get("code")
        lat = item.get("lat")
        lon = item.get("lon")
        if code is None or lat is None or lon is None:
            continue
        out.append(PowerPlant(code=str(code), lat=float(lat), lon=float(lon)))
    return out

