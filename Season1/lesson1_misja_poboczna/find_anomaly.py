import argparse
import csv
import io
import math
import os
from pathlib import Path
from typing import Any
from urllib.request import urlopen


def load_env_file(env_path: Path) -> None:
    """Wczytuje podstawowe zmienne z pliku .env do os.environ."""
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


def load_csv(source: str) -> list[dict[str, str]]:
    """Wczytuje CSV z pliku lokalnego albo URL i zwraca listę rekordów."""
    if source.startswith("http://") or source.startswith("https://"):
        with urlopen(source, timeout=30) as response:  # noqa: S310
            content = response.read().decode("utf-8")
    else:
        content = Path(source).read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(content)))


def _normalized(value: Any) -> str:
    """Normalizuje wartość do postaci tekstowej używanej w porównaniach."""
    return str(value or "").strip().casefold()


def anomaly_scores(rows: list[dict[str, str]]) -> list[float]:
    """Liczy wynik anomalii dla każdego wiersza na podstawie rzadkości wartości."""
    if not rows:
        return []

    columns = list(rows[0].keys())
    frequencies: dict[str, dict[str, int]] = {col: {} for col in columns}

    for row in rows:
        for col in columns:
            value = _normalized(row.get(col))
            if not value:
                continue
            frequencies[col][value] = frequencies[col].get(value, 0) + 1

    total = len(rows)
    scores: list[float] = []
    for row in rows:
        score = 0.0
        for col in columns:
            value = _normalized(row.get(col))
            if not value:
                continue
            freq = frequencies[col].get(value, 1)
            probability = freq / total
            score += -math.log(probability)
        scores.append(score)
    return scores


def explain_row(row: dict[str, str], rows: list[dict[str, str]]) -> list[str]:
    """Zwraca listę pól, w których rekord najbardziej odstaje od innych."""
    if not rows:
        return []
    columns = list(row.keys())
    total = len(rows)
    reasons: list[tuple[float, str]] = []

    for col in columns:
        value = _normalized(row.get(col))
        if not value:
            continue
        freq = sum(1 for r in rows if _normalized(r.get(col)) == value)
        rarity = 1 - (freq / total)
        reasons.append((rarity, f"{col}={row.get(col)} (wystąpień: {freq}/{total})"))

    reasons.sort(reverse=True, key=lambda x: x[0])
    return [msg for _, msg in reasons[:3]]


def find_anomaly(rows: list[dict[str, str]]) -> tuple[dict[str, str], float]:
    """Wybiera rekord o najwyższym wyniku anomalii."""
    if not rows:
        raise ValueError("CSV jest puste.")
    scores = anomaly_scores(rows)
    idx = max(range(len(scores)), key=lambda i: scores[i])
    return rows[idx], scores[idx]


def main() -> None:
    current_dir = Path(__file__).resolve().parent
    root_dir = current_dir.parent
    load_env_file(current_dir / ".env")
    load_env_file(root_dir / ".env")

    default_source = os.getenv("PEOPLE_CSV_URL")
    parser = argparse.ArgumentParser(
        description="Szukanie anomalii w CSV (rekord, który nie pasuje do reszty)."
    )
    parser.add_argument(
        "source",
        nargs="?",
        default=default_source,
        help="Ścieżka do pliku CSV albo URL. Domyślnie PEOPLE_CSV_URL z .env.",
    )
    args = parser.parse_args()
    if not args.source:
        raise SystemExit(
            "Brak źródła CSV. Podaj argument source lub ustaw PEOPLE_CSV_URL w .env."
        )

    rows = load_csv(args.source)
    anomaly, score = find_anomaly(rows)
    reasons = explain_row(anomaly, rows)

    print("Był anomalią i nie pasował do reszty.")
    print(f"Anomaly score: {score:.4f}")
    print("Najbardziej odstający rekord:")
    print(anomaly)
    if reasons:
        print("Powody:")
        for reason in reasons:
            print(f"- {reason}")


if __name__ == "__main__":
    main()
