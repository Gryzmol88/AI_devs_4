"""Budowanie akcji API tworzących docelową strukturę filesystem."""

from __future__ import annotations

import json

from .models import FsAction, NormalizedKnowledge


def _city_link(city_slug: str) -> str:
    """Buduje link markdown do pliku miasta.

    Args:
        city_slug: Znormalizowana nazwa miasta używana w ścieżce.

    Returns:
        str: Link markdown wskazujący plik miasta.
    """

    return f"[{city_slug}](/miasta/{city_slug})"


def build_fs_actions(data: NormalizedKnowledge) -> list[FsAction]:
    """Buduje listę akcji API tworzących strukturę wymaganych katalogów i plików.

    Args:
        data: Dane po normalizacji.

    Returns:
        list[FsAction]: Kolejność operacji do wykonania przez API.
    """

    actions: list[FsAction] = [
        FsAction(action="createDirectory", path="/miasta"),
        FsAction(action="createDirectory", path="/osoby"),
        FsAction(action="createDirectory", path="/towary"),
    ]

    for city_slug, needs in sorted(data.city_needs.items()):
        content = json.dumps(needs, ensure_ascii=True, indent=2)
        actions.append(
            FsAction(action="createFile", path=f"/miasta/{city_slug}", content=content)
        )

    for person_slug, city_slug in sorted(data.person_to_city.items()):
        person_full_name = data.person_display_name.get(
            person_slug, person_slug.replace("_", " ")
        )
        content = f"{person_full_name}\n{_city_link(city_slug)}"
        actions.append(
            FsAction(
                action="createFile",
                path=f"/osoby/{person_slug}",
                content=content,
            )
        )

    for item_slug, cities in sorted(data.item_to_cities.items()):
        links = "\n".join(_city_link(city) for city in sorted(cities))
        actions.append(
            FsAction(
                action="createFile",
                path=f"/towary/{item_slug}",
                content=links,
            )
        )

    return actions
