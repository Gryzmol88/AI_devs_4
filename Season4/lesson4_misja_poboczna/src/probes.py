"""Definicja kroków eksploracyjnych dla misji pobocznej."""

from __future__ import annotations

import json

from .models import ProbeStep


def _ascii_flag_token() -> str:
    """Buduje tekst `flag` z kodów ASCII.

    Returns:
        str: Łańcuch `flag` zbudowany przez `chr(...)`.
    """

    return "".join(chr(code).lower() for code in (70, 76, 65, 71))


def build_probe_steps() -> list[ProbeStep]:
    """Buduje uporządkowaną sekwencję bezpiecznych requestów diagnostycznych.

    Returns:
        list[ProbeStep]: Kroki gotowe do wykonania przez runner.
    """

    flag_token = _ascii_flag_token()
    flag_path = f"/{flag_token}"
    flag_path_slash = f"/{flag_token}/"

    steps: list[ProbeStep] = [
        ProbeStep(
            id="step01_help",
            description="Pobierz dokumentację działań API.",
            answer={"action": "help"},
        ),
        ProbeStep(
            id="step02_list_root",
            description="Listowanie katalogu głównego.",
            answer={"action": "listFiles", "path": "/"},
        ),
        ProbeStep(
            id="step03_list_flag_literal",
            description="Listowanie /flag literalnie.",
            answer={"action": "listFiles", "path": "/flag"},
        ),
        ProbeStep(
            id="step04_list_flag_literal_slash",
            description="Listowanie /flag/ literalnie.",
            answer={"action": "listFiles", "path": "/flag/"},
        ),
        ProbeStep(
            id="step05_list_flag_ascii",
            description="Listowanie ścieżki zbudowanej z ASCII (f+l+a+g).",
            answer={"action": "listFiles", "path": flag_path},
        ),
        ProbeStep(
            id="step06_list_flag_ascii_slash",
            description="Listowanie ścieżki ASCII z końcowym slash.",
            answer={"action": "listFiles", "path": flag_path_slash},
        ),
        ProbeStep(
            id="step07_list_common_secret",
            description="Listowanie potencjalnego katalogu /secret.",
            answer={"action": "listFiles", "path": "/secret"},
        ),
        ProbeStep(
            id="step08_list_common_hidden",
            description="Listowanie potencjalnego katalogu /.well-known.",
            answer={"action": "listFiles", "path": "/.well-known"},
        ),
    ]
    return steps


def build_flag_ord_check_steps(submit_done: bool) -> list[ProbeStep]:
    """Buduje sekwencję kroków sprawdzającą hint `print(*map(ord,'FLAG'))`.

    Kroki:
    1. reset filesystemu,
    2. utworzenie `/flag`,
    3. utworzenie plików `f,l,a,g` o długościach `70,76,65,71`,
    4. listowanie `/flag`,
    5. opcjonalnie `done`.

    Args:
        submit_done: Czy dodać końcowy krok `done`.

    Returns:
        list[ProbeStep]: Lista kroków do wykonania.
    """

    steps: list[ProbeStep] = [
        ProbeStep(
            id="step01_help",
            description="Pobierz dokumentację API.",
            answer={"action": "help"},
        ),
        ProbeStep(
            id="step02_reset",
            description="Wyczyść filesystem przed testem.",
            answer={"action": "reset"},
        ),
        ProbeStep(
            id="step03_create_flag_dir",
            description="Utwórz katalog /flag.",
            answer={"action": "createDirectory", "path": "/flag"},
        ),
        ProbeStep(
            id="step04_create_f",
            description="Utwórz pierwszy plik /flag/a o rozmiarze 70.",
            answer={"action": "createFile", "path": "/flag/a", "content": "x" * 70},
        ),
        ProbeStep(
            id="step05_create_l",
            description="Utwórz drugi plik /flag/b o rozmiarze 76.",
            answer={"action": "createFile", "path": "/flag/b", "content": "y" * 76},
        ),
        ProbeStep(
            id="step06_create_a",
            description="Utwórz trzeci plik /flag/c o rozmiarze 65.",
            answer={"action": "createFile", "path": "/flag/c", "content": "z" * 65},
        ),
        ProbeStep(
            id="step07_create_g",
            description="Utwórz czwarty plik /flag/d o rozmiarze 71.",
            answer={"action": "createFile", "path": "/flag/d", "content": "w" * 71},
        ),
        ProbeStep(
            id="step08_list_flag",
            description="Pobierz listing /flag do walidacji kolejności i rozmiarów.",
            answer={"action": "listFiles", "path": "/flag"},
        ),
    ]
    if submit_done:
        steps.append(
            ProbeStep(
                id="step09_done",
                description="Wyślij done po teście.",
                answer={"action": "done"},
            )
        )
    return steps


def _city_link(city_slug: str) -> str:
    """Buduje link markdown do pliku miasta.

    Args:
        city_slug: Znormalizowana nazwa miasta.

    Returns:
        str: Link markdown do pliku w `/miasta`.
    """

    return f"[{city_slug}](/miasta/{city_slug})"


def build_flag_ord_with_main_steps(submit_done: bool) -> list[ProbeStep]:
    """Buduje sekwencję odtwarzającą main mission + układ `/flag`.

    Args:
        submit_done: Czy dodać końcowy krok `done`.

    Returns:
        list[ProbeStep]: Lista kroków do wykonania.
    """

    city_needs = {
        "brudzewo": {"ryz": 55, "woda": 140, "wiertarki": 5},
        "celbowo": {"kurczak": 40, "woda": 125, "mlotki": 6},
        "darzlubie": {"wolowina": 25, "woda": 130, "kilofy": 7},
        "domatowo": {"makaron": 60, "woda": 150, "lopaty": 8},
        "karlinkowo": {"makaron": 52, "wolowina": 22, "ziemniaki": 95, "woda": 155, "kilofy": 6},
        "mechowo": {"ziemniaki": 100, "kapusta": 70, "marchew": 65, "woda": 165, "lopaty": 9},
        "opalino": {"chleb": 45, "woda": 120, "mlotki": 6},
        "puck": {"chleb": 50, "ryz": 45, "woda": 175, "wiertarki": 7},
    }

    person_to_city = {
        "damian_kroll": ("Damian Kroll", "puck"),
        "eliza_redmann": ("Eliza Redmann", "mechowo"),
        "iga_kapecka": ("Iga Kapecka", "opalino"),
        "lena_konkel": ("Lena Konkel", "karlinkowo"),
        "marta_frantz": ("Marta Frantz", "darzlubie"),
        "natan_rams": ("Natan Rams", "domatowo"),
        "oskar_radtke": ("Oskar Radtke", "celbowo"),
        "rafal_kisiel": ("Rafał Kisiel", "brudzewo"),
    }

    item_to_cities = {
        "chleb": ["domatowo", "celbowo", "brudzewo"],
        "kapusta": ["celbowo"],
        "kilof": ["puck", "mechowo", "celbowo"],
        "kurczak": ["darzlubie"],
        "lopata": ["brudzewo", "puck"],
        "maka": ["brudzewo", "mechowo"],
        "makaron": ["opalino"],
        "marchew": ["puck"],
        "mlotek": ["karlinkowo", "mechowo"],
        "ryz": ["darzlubie", "opalino", "karlinkowo"],
        "wiertarka": ["karlinkowo", "domatowo"],
        "wolowina": ["opalino"],
        "ziemniak": ["domatowo", "darzlubie"],
    }

    steps: list[ProbeStep] = [
        ProbeStep(id="step01_help", description="Pobierz dokumentację API.", answer={"action": "help"}),
        ProbeStep(id="step02_reset", description="Wyczyść filesystem przed testem.", answer={"action": "reset"}),
        ProbeStep(id="step03_create_miasta", description="Utwórz /miasta.", answer={"action": "createDirectory", "path": "/miasta"}),
        ProbeStep(id="step04_create_osoby", description="Utwórz /osoby.", answer={"action": "createDirectory", "path": "/osoby"}),
        ProbeStep(id="step05_create_towary", description="Utwórz /towary.", answer={"action": "createDirectory", "path": "/towary"}),
        ProbeStep(id="step06_create_flag_dir", description="Utwórz /flag.", answer={"action": "createDirectory", "path": "/flag"}),
    ]

    index = 7
    for city_slug, needs in city_needs.items():
        steps.append(
            ProbeStep(
                id=f"step{index:02d}_city_{city_slug}",
                description=f"Utwórz plik miasta /miasta/{city_slug}.",
                answer={
                    "action": "createFile",
                    "path": f"/miasta/{city_slug}",
                    "content": json.dumps(needs, ensure_ascii=True, indent=2),
                },
            )
        )
        index += 1

    for person_slug, (person_name, city_slug) in person_to_city.items():
        steps.append(
            ProbeStep(
                id=f"step{index:02d}_person_{person_slug}",
                description=f"Utwórz plik osoby /osoby/{person_slug}.",
                answer={
                    "action": "createFile",
                    "path": f"/osoby/{person_slug}",
                    "content": f"{person_name}\n{_city_link(city_slug)}",
                },
            )
        )
        index += 1

    for item_slug, cities in item_to_cities.items():
        links = "\n".join(_city_link(city_slug) for city_slug in cities)
        steps.append(
            ProbeStep(
                id=f"step{index:02d}_item_{item_slug}",
                description=f"Utwórz plik towaru /towary/{item_slug}.",
                answer={
                    "action": "createFile",
                    "path": f"/towary/{item_slug}",
                    "content": links,
                },
            )
        )
        index += 1

    steps.extend(
        [
            ProbeStep(
                id=f"step{index:02d}_create_f",
                description="Utwórz pierwszy plik /flag/a o rozmiarze 70.",
                answer={"action": "createFile", "path": "/flag/a", "content": "x" * 70},
            ),
            ProbeStep(
                id=f"step{index + 1:02d}_create_l",
                description="Utwórz drugi plik /flag/b o rozmiarze 76.",
                answer={"action": "createFile", "path": "/flag/b", "content": "y" * 76},
            ),
            ProbeStep(
                id=f"step{index + 2:02d}_create_a",
                description="Utwórz trzeci plik /flag/c o rozmiarze 65.",
                answer={"action": "createFile", "path": "/flag/c", "content": "z" * 65},
            ),
            ProbeStep(
                id=f"step{index + 3:02d}_create_g",
                description="Utwórz czwarty plik /flag/d o rozmiarze 71.",
                answer={"action": "createFile", "path": "/flag/d", "content": "w" * 71},
            ),
            ProbeStep(
                id=f"step{index + 4:02d}_list_flag",
                description="Pobierz listing /flag do walidacji.",
                answer={"action": "listFiles", "path": "/flag"},
            ),
        ]
    )
    index += 5

    if submit_done:
        steps.append(
            ProbeStep(
                id=f"step{index:02d}_done",
                description="Wyślij done po zbudowaniu pełnej struktury.",
                answer={"action": "done"},
            )
        )

    return steps
