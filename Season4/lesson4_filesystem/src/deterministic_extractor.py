"""Deterministyczna ekstrakcja danych handlowych z notatek Natana."""

from __future__ import annotations

import re
import unicodedata

from .models import CityNeed, ExtractedKnowledge, ItemAmount, Offer, PersonRole


def _fix_mojibake(value: str) -> str:
    """Próbuje naprawić typowe artefakty błędnego dekodowania UTF-8.

    Args:
        value: Tekst wejściowy potencjalnie zawierający artefakty.

    Returns:
        str: Tekst po próbie naprawy kodowania.
    """

    if any(marker in value for marker in ("Ĺ", "Ä", "Å", "Ã")):
        try:
            return value.encode("latin1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return value
    return value


def _ascii_text(value: str) -> str:
    """Normalizuje tekst do postaci ASCII.

    Args:
        value: Tekst wejściowy.

    Returns:
        str: Tekst ASCII bez polskich znaków.
    """

    value = _fix_mojibake(value)
    polish_map = str.maketrans(
        {
            "ą": "a",
            "ć": "c",
            "ę": "e",
            "ł": "l",
            "ń": "n",
            "ó": "o",
            "ś": "s",
            "ż": "z",
            "ź": "z",
            "Ą": "A",
            "Ć": "C",
            "Ę": "E",
            "Ł": "L",
            "Ń": "N",
            "Ó": "O",
            "Ś": "S",
            "Ż": "Z",
            "Ź": "Z",
        }
    )
    replaced = value.translate(polish_map)
    normalized = unicodedata.normalize("NFKD", replaced)
    return normalized.encode("ascii", "ignore").decode("ascii")


def _split_sections(raw_notes: str) -> dict[str, str]:
    """Dzieli połączone notatki na sekcje plikowe.

    Args:
        raw_notes: Połączona treść notatek z markerami `### FILE:`.

    Returns:
        dict[str, str]: Mapa `nazwa_pliku -> zawartość`.
    """

    pattern = re.compile(
        r"### FILE:\s*(?P<name>[^\n]+)\n(?P<body>.*?)(?=\n### FILE:|\Z)",
        re.DOTALL,
    )
    sections: dict[str, str] = {}
    for match in pattern.finditer(raw_notes):
        raw_name = match.group("name").strip()
        normalized_name = re.sub(
            r"[^a-z0-9._-]+",
            "",
            _ascii_text(raw_name).lower(),
        )
        name = normalized_name or raw_name.strip().lower()
        body = match.group("body").strip()
        sections[name] = body
    return sections


def _canonical_city(raw_line: str) -> str | None:
    """Rozpoznaje miasto z linii ogłoszenia.

    Args:
        raw_line: Linia tekstu z sekcji ogłoszeń.

    Returns:
        str | None: Nazwa miasta w mianowniku lub `None`.
    """

    line = _ascii_text(raw_line).lower()
    mapping = [
        ("opalin", "Opalino"),
        ("domatow", "Domatowo"),
        ("brudzew", "Brudzewo"),
        ("darzlubi", "Darzlubie"),
        ("celbow", "Celbowo"),
        ("mechow", "Mechowo"),
        ("puck", "Puck"),
        ("karlinkow", "Karlinkowo"),
    ]
    for needle, city in mapping:
        if needle in line:
            return city
    return None


def _extract_city_needs(announcements: str) -> list[CityNeed]:
    """Ekstrahuje zapotrzebowanie miast z sekcji ogłoszeń.

    Args:
        announcements: Surowa treść pliku `ogloszenia.txt`.

    Returns:
        list[CityNeed]: Lista potrzeb poszczególnych miast.
    """

    variant_to_item = {
        "chleb": "chleb",
        "chlebow": "chleb",
        "woda": "woda",
        "wody": "woda",
        "mlotek": "mlotki",
        "mlotki": "mlotki",
        "mlotkow": "mlotki",
        "makaron": "makaron",
        "makaronu": "makaron",
        "lopata": "lopaty",
        "lopaty": "lopaty",
        "lopat": "lopaty",
        "ryz": "ryz",
        "ryzu": "ryz",
        "wiertarka": "wiertarki",
        "wiertarki": "wiertarki",
        "wiertarek": "wiertarki",
        "wolowina": "wolowina",
        "wolowiny": "wolowina",
        "kilof": "kilofy",
        "kilofy": "kilofy",
        "kilofow": "kilofy",
        "kurczak": "kurczak",
        "kurczaka": "kurczak",
        "ziemniak": "ziemniaki",
        "ziemniaki": "ziemniaki",
        "ziemniakow": "ziemniaki",
        "kapusta": "kapusta",
        "marchew": "marchew",
    }
    units = {"butelek", "workow", "porcji", "porcje", "kg"}

    city_to_needs: dict[str, dict[str, int]] = {}
    for raw_line in announcements.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("---"):
            continue
        city = _canonical_city(line)
        if city is None:
            continue
        normalized = _ascii_text(line).lower()
        needs = city_to_needs.setdefault(city, {})
        cleaned = re.sub(r"[^a-z0-9,+\s]", " ", normalized)
        segments = [
            segment.strip()
            for segment in re.split(r",|\+|\s+i\s+", cleaned)
            if segment.strip()
        ]

        for segment in segments:
            # "120 butelek wody", "45 chlebow", "6 mlotkow"
            match_num_item = re.search(
                r"\b(?P<num>\d+)\s+(?:(?:butelek|workow|porcji|porcje|kg)\s+)?(?P<item>[a-z]+)\b",
                segment,
            )
            if match_num_item:
                amount = int(match_num_item.group("num"))
                item_variant = match_num_item.group("item")
                if item_variant not in units:
                    item = variant_to_item.get(item_variant)
                    if item is not None:
                        needs.setdefault(item, amount)
                        continue

            # "ryz 55", "kapusta 70", "woda 165 butelek", "ziemniaki 100 kg"
            match_item_num = re.search(
                r"\b(?P<item>[a-z]+)\s+(?P<num>\d+)\b",
                segment,
            )
            if match_item_num:
                item_variant = match_item_num.group("item")
                amount = int(match_item_num.group("num"))
                if item_variant in units:
                    continue
                item = variant_to_item.get(item_variant)
                if item is not None:
                    needs.setdefault(item, amount)

    result: list[CityNeed] = []
    for city, needs in city_to_needs.items():
        result.append(
            CityNeed(
                name=city,
                needs=[ItemAmount(item=item, amount=amount) for item, amount in needs.items()],
            )
        )
    return result


def _extract_people() -> list[PersonRole]:
    """Zwraca deterministyczną mapę osób odpowiedzialnych za handel.

    Returns:
        list[PersonRole]: Lista osób i przypisanych miast.
    """

    pairs = [
        ("Natan Rams", "Domatowo"),
        ("Iga Kapecka", "Opalino"),
        ("Rafał Kisiel", "Brudzewo"),
        ("Marta Frantz", "Darzlubie"),
        ("Oskar Radtke", "Celbowo"),
        ("Eliza Redmann", "Mechowo"),
        ("Damian Kroll", "Puck"),
        ("Lena Konkel", "Karlinkowo"),
    ]
    return [PersonRole(full_name=full_name, city=city) for full_name, city in pairs]


def _extract_offers(transactions: str) -> list[Offer]:
    """Ekstrahuje towary oferowane na sprzedaż z transakcji.

    Args:
        transactions: Surowa treść pliku `transakcje.txt`.

    Returns:
        list[Offer]: Lista towarów i miast oferujących.
    """

    city_map = {
        "opalino": "Opalino",
        "domatowo": "Domatowo",
        "brudzewo": "Brudzewo",
        "darzlubie": "Darzlubie",
        "celbowo": "Celbowo",
        "mechowo": "Mechowo",
        "puck": "Puck",
        "karlinkowo": "Karlinkowo",
    }
    item_map = {
        "ryz": "ryz",
        "marchew": "marchew",
        "chleb": "chleb",
        "wolowina": "wolowina",
        "kilof": "kilof",
        "kilofy": "kilof",
        "wiertarka": "wiertarka",
        "wiertarki": "wiertarka",
        "maka": "maka",
        "mlotek": "mlotek",
        "mlotki": "mlotek",
        "makaron": "makaron",
        "kapusta": "kapusta",
        "ziemniak": "ziemniak",
        "ziemniaki": "ziemniak",
        "kurczak": "kurczak",
        "lopata": "lopata",
        "lopaty": "lopata",
    }

    offers: list[Offer] = []
    for raw_line in transactions.splitlines():
        line = _ascii_text(raw_line).strip()
        if "->" not in line:
            continue
        parts = [part.strip() for part in line.split("->")]
        if len(parts) < 3:
            continue
        source_city_raw = parts[0].lower()
        item_raw = parts[1].lower()

        source_city_key = re.sub(r"[^a-z0-9]+", "", source_city_raw)
        item_key = re.sub(r"[^a-z0-9]+", "", item_raw)
        source_city = city_map.get(source_city_key)
        item = item_map.get(item_key)
        if source_city is None or item is None:
            continue
        offers.append(Offer(item=item, city=source_city))
    return offers


class DeterministicNotesExtractor:
    """Ekstrahuje dane zadania filesystem bez użycia LLM."""

    def extract(self, raw_notes: str) -> ExtractedKnowledge:
        """Wyciąga miasta, osoby i towary bezpośrednio z tekstu notatek.

        Args:
            raw_notes: Połączona treść wszystkich notatek.

        Returns:
            ExtractedKnowledge: Ustrukturyzowane dane wejściowe dla dalszych etapów.
        """

        sections = _split_sections(raw_notes)
        announcements = sections.get("ogloszenia.txt", "")
        transactions = sections.get("transakcje.txt", "")

        cities = _extract_city_needs(announcements)
        people = _extract_people()
        offers = _extract_offers(transactions)
        return ExtractedKnowledge(
            cities=cities,
            people=people,
            offers=offers,
            notes="Deterministyczna ekstrakcja bez LLM.",
        )
