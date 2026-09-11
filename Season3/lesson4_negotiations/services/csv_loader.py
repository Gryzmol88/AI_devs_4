"""Ładowanie i parsowanie danych CSV o ofertach miast."""

from __future__ import annotations

import csv
import io
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from config import Settings
from models import ListingRecord
from services.text_utils import normalize_text


@dataclass(slots=True)
class CsvKnowledgeBase:
    """Wczytuje rekordy ofert z jednego lub wielu plików CSV.

    Atrybuty:
        settings: Konfiguracja aplikacji.
    """

    settings: Settings

    def discover_csv_urls(self) -> list[str]:
        """Wyszukuje adresy plików CSV dostępnych pod bazowym URL.

        Returns:
            Lista adresów URL do plików CSV.
        """

        base_url = self.settings.csv_base_url.strip()
        if base_url.lower().endswith(".csv"):
            return [base_url]

        request = urllib.request.Request(base_url, method="GET")
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            html = response.read().decode("utf-8", errors="replace")

        matches = re.findall(r'href=["\']([^"\']+\.csv)["\']', html, flags=re.IGNORECASE)
        urls: list[str] = []
        for match in matches:
            absolute_url = urllib.parse.urljoin(base_url, match)
            if absolute_url not in urls:
                urls.append(absolute_url)
        return urls

    def load_records(self) -> list[ListingRecord]:
        """Wczytuje i normalizuje rekordy ofert ze wszystkich znalezionych CSV.

        Returns:
            Lista rekordów z nazwami miast i przedmiotów.
        """

        csv_urls = self.discover_csv_urls()
        rows_by_url = {url: self._load_csv_rows(url) for url in csv_urls}

        cities_rows = self._find_dataset(rows_by_url, required_columns={"name", "code"}, preferred_name="cities")
        items_rows = self._find_dataset(rows_by_url, required_columns={"name", "code"}, preferred_name="items")
        connections_rows = self._find_dataset(
            rows_by_url,
            required_columns={"itemcode", "citycode"},
            preferred_name="connections",
        )

        if cities_rows and items_rows and connections_rows:
            return self._join_from_codes(
                cities_rows=cities_rows[1],
                items_rows=items_rows[1],
                connections_rows=connections_rows[1],
                source_file=connections_rows[0],
            )

        # Fallback dla nieznanych struktur.
        records: list[ListingRecord] = []
        for csv_url, rows in rows_by_url.items():
            records.extend(self._convert_rows(rows, csv_url))
        return records

    def _load_csv_rows(self, csv_url: str) -> list[dict[str, str]]:
        """Pobiera i parsuje pojedynczy plik CSV jako listę wierszy.

        Args:
            csv_url: URL pliku CSV.

        Returns:
            Lista słowników reprezentujących wiersze CSV.
        """

        request = urllib.request.Request(csv_url, method="GET")
        with urllib.request.urlopen(request, timeout=self.settings.request_timeout_seconds) as response:
            payload = response.read()

        text = payload.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized_row = {str(k): "" if v is None else str(v) for k, v in row.items() if k is not None}
            rows.append(normalized_row)
        return rows

    def _convert_rows(self, rows: list[dict[str, str]], source_file: str) -> list[ListingRecord]:
        """Mapuje surowe wiersze CSV na rekordy domenowe.

        Args:
            rows: Wiersze CSV jako słowniki.
            source_file: URL źródłowego pliku.

        Returns:
            Lista rekordów domenowych gotowych do indeksowania.
        """

        converted: list[ListingRecord] = []
        for row in rows:
            city = self._extract_value(
                row,
                preferred_keys=("city", "miasto", "town", "miejscowosc", "location"),
                fallback_index=0,
            )
            item = self._extract_value(
                row,
                preferred_keys=("item", "product", "przedmiot", "towar", "name", "nazwa"),
                fallback_index=1,
            )
            if not city or not item:
                continue

            city_norm = normalize_text(city)
            item_norm = normalize_text(item)
            if not city_norm or not item_norm:
                continue

            converted.append(
                ListingRecord(
                    city=city.strip(),
                    item=item.strip(),
                    city_norm=city_norm,
                    item_norm=item_norm,
                    source_file=source_file,
                    raw=row,
                )
            )
        return converted

    def _find_dataset(
        self,
        rows_by_url: dict[str, list[dict[str, str]]],
        required_columns: set[str],
        preferred_name: str,
    ) -> tuple[str, list[dict[str, str]]] | None:
        """Wyszukuje zestaw wierszy zawierający wymagane kolumny.

        Args:
            rows_by_url: Słownik URL -> wiersze CSV.
            required_columns: Zestaw wymaganych nazw kolumn.
            preferred_name: Fragment nazwy pliku preferowanego przy wielu dopasowaniach.

        Returns:
            Krotka `(url, rows)` lub `None` gdy brak dopasowania.
        """

        candidates: list[tuple[str, list[dict[str, str]]]] = []
        for url, rows in rows_by_url.items():
            if not rows:
                continue
            keys = {str(key).lower().strip() for key in rows[0].keys()}
            if required_columns.issubset(keys):
                candidates.append((url, rows))

        if not candidates:
            return None
        for candidate in candidates:
            if preferred_name.lower() in candidate[0].lower():
                return candidate
        return candidates[0]

    def _join_from_codes(
        self,
        cities_rows: list[dict[str, str]],
        items_rows: list[dict[str, str]],
        connections_rows: list[dict[str, str]],
        source_file: str,
    ) -> list[ListingRecord]:
        """Łączy dane `cities/items/connections` po kodach.

        Args:
            cities_rows: Wiersze z mapą kod miasta -> nazwa miasta.
            items_rows: Wiersze z mapą kod przedmiotu -> nazwa przedmiotu.
            connections_rows: Wiersze relacji kod przedmiotu -> kod miasta.
            source_file: Źródłowy plik relacji.

        Returns:
            Lista rekordów ofert gotowych do indeksowania.
        """

        city_by_code: dict[str, str] = {}
        for row in cities_rows:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            if code and name:
                city_by_code[code] = name

        item_by_code: dict[str, str] = {}
        for row in items_rows:
            code = row.get("code", "").strip()
            name = row.get("name", "").strip()
            if code and name:
                item_by_code[code] = name

        records: list[ListingRecord] = []
        for row in connections_rows:
            item_code = row.get("itemCode", row.get("itemcode", "")).strip()
            city_code = row.get("cityCode", row.get("citycode", "")).strip()
            city = city_by_code.get(city_code, "")
            item = item_by_code.get(item_code, "")
            if not city or not item:
                continue

            records.append(
                ListingRecord(
                    city=city,
                    item=item,
                    city_norm=normalize_text(city),
                    item_norm=normalize_text(item),
                    source_file=source_file,
                    raw={
                        "cityCode": city_code,
                        "itemCode": item_code,
                        "city": city,
                        "item": item,
                    },
                )
            )
        return records

    def _extract_value(
        self,
        row: dict[str, str],
        preferred_keys: tuple[str, ...],
        fallback_index: int,
    ) -> str:
        """Pobiera wartość z wiersza po nazwie klucza lub pozycji kolumny.

        Args:
            row: Wiersz CSV.
            preferred_keys: Lista preferowanych nazw kolumn.
            fallback_index: Indeks kolumny używany jako fallback.

        Returns:
            Odczytana wartość tekstowa lub pusty napis.
        """

        lowered_map = {key.lower().strip(): value for key, value in row.items()}
        for preferred in preferred_keys:
            for key, value in lowered_map.items():
                if preferred in key:
                    return value.strip()

        values = list(row.values())
        if 0 <= fallback_index < len(values):
            return values[fallback_index].strip()
        return ""
