"""Rozwiązywanie identyfikatorów rekordów potrzebnych do zadania `okoeditor`."""

from typing import Any


class OkoIdResolver:
    """Dobiera rekordy `id` dla wymaganych aktualizacji.

    Strategia opiera się na dopasowaniu słów kluczowych w snippetach.
    """

    def resolve(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Wyznacza rekordy potrzebne do wykonania trzech aktualizacji.

        Args:
            records: Lista rekordów odczytanych z panelu.

        Returns:
            Słownik z polami:
            - `resolved`: mapowanie nazwy celu na rekord,
            - `errors`: lista problemów uniemożliwiających pełne dopasowanie.
        """

        resolved: dict[str, Any] = {}
        errors: list[str] = []

        skolwin_incident = self._pick_best(
            records=records,
            page="incydenty",
            must_include=["skolwin"],
            optional_include=["pojazd", "ludzi", "człow", "ruch"],
            must_exclude=[],
            excluded_ids=set(),
        )
        if skolwin_incident:
            resolved["skolwin_incident"] = skolwin_incident
        else:
            errors.append("Nie znaleziono rekordu incydentu dotyczącego Skolwin.")

        skolwin_task = self._pick_best(
            records=records,
            page="zadania",
            must_include=["skolwin"],
            optional_include=["zadani", "nagr", "okolic", "analiza", "niewykonane"],
            must_exclude=["operatorów dyżurnych"],
            excluded_ids=set(),
        )
        if skolwin_task:
            resolved["skolwin_task"] = skolwin_task
        else:
            errors.append("Nie znaleziono rekordu zadania dotyczącego Skolwin.")

        komarowo_incident = self._pick_best(
            records=records,
            page="incydenty",
            must_include=["komarow"],
            optional_include=["ruch", "ludzi", "człow"],
            must_exclude=[],
            excluded_ids={str(skolwin_incident.get("id"))} if skolwin_incident else set(),
        )
        if not komarowo_incident:
            komarowo_incident = self._pick_best(
                records=records,
                page="incydenty",
                must_include=[],
                optional_include=["incydent", "ruch", "ludzi", "pojazd", "prob", "move"],
                must_exclude=["skolwin"],
                excluded_ids={str(skolwin_incident.get("id"))} if skolwin_incident else set(),
            )
        if komarowo_incident:
            resolved["komarowo_incident"] = komarowo_incident
        else:
            errors.append("Nie znaleziono rekordu incydentu do przekierowania na Komarowo.")

        return {"resolved": resolved, "errors": errors}

    def _pick_best(
        self,
        records: list[dict[str, Any]],
        page: str,
        must_include: list[str],
        optional_include: list[str],
        must_exclude: list[str],
        excluded_ids: set[str],
    ) -> dict[str, Any] | None:
        """Wybiera rekord o najwyższym dopasowaniu słów kluczowych.

        Args:
            records: Lista rekordów do przeszukania.
            page: Oczekiwana strona (`incydenty`/`zadania`/`notatki`).
            must_include: Słowa, które muszą wystąpić w snippecie.
            optional_include: Słowa dodatkowo punktujące dopasowanie.
            must_exclude: Słowa, które nie mogą wystąpić w tekście.
            excluded_ids: Zbiór ID wykluczonych z wyboru.

        Returns:
            Najlepiej dopasowany rekord lub `None`.
        """

        candidates: list[tuple[int, dict[str, Any]]] = []
        for record in records:
            if record.get("page") != page:
                continue
            if str(record.get("id")) in excluded_ids:
                continue

            search_text = str(record.get("search_text", "")).lower()
            if not search_text:
                search_text = str(record.get("snippet", "")).lower()

            if must_include and not all(token in search_text for token in must_include):
                continue
            if must_exclude and any(token in search_text for token in must_exclude):
                continue

            score = 0
            score += sum(4 for token in must_include if token in search_text)
            score += sum(1 for token in optional_include if token in search_text)
            score += 2 if bool(record.get("has_skolwin")) else 0
            score += 1 if bool(record.get("has_komarowo")) else 0
            candidates.append((score, record))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]
