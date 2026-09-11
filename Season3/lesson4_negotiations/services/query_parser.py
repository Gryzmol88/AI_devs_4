"""Parser zapytań w języku naturalnym do ekstrakcji nazw przedmiotów."""

from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass

from services.openrouter_client import OpenRouterClient
from services.text_utils import normalize_text, unique_preserve_order


@dataclass(slots=True)
class QueryParser:
    """Wykrywa przedmioty w zapytaniu na podstawie heurystyk i fallbacku LLM.

    Atrybuty:
        llm_client: Opcjonalny klient OpenRouter.
    """

    llm_client: OpenRouterClient | None = None

    def extract_items(self, query: str, known_items: list[str]) -> list[str]:
        """Wydobywa listę przedmiotów z zapytania.

        Args:
            query: Treść wejściowa w języku naturalnym.
            known_items: Lista znanych nazw przedmiotów.

        Returns:
            Lista nazw przedmiotów dopasowanych do `known_items`.
        """

        items_from_json = self._extract_from_json_like(query)
        if items_from_json:
            return self._resolve_terms(items_from_json, known_items)

        exact_full_match = self._extract_exact_full_matches(query, known_items)
        if exact_full_match:
            return exact_full_match

        best_scored = self._best_item_by_query_score(query, known_items)
        if best_scored is not None:
            return [best_scored]

        terms = self._extract_candidate_terms(query)
        resolved = self._resolve_terms(terms, known_items)
        if resolved:
            # W trybie naturalnego pytania zwracamy jeden najlepszy przedmiot.
            return resolved[:1]

        if self.llm_client and self.llm_client.is_enabled():
            llm_items = self.llm_client.extract_items(query=query, known_items=known_items)
            resolved = self._resolve_terms(llm_items, known_items)
            if resolved:
                return resolved[:1]

        return []

    def _extract_exact_full_matches(self, query: str, known_items: list[str]) -> list[str]:
        """Wyszukuje dokładne dopasowania pełnej nazwy przedmiotu w treści zapytania.

        Args:
            query: Treść zapytania.
            known_items: Lista znanych nazw przedmiotów.

        Returns:
            Lista przedmiotów dopasowanych dokładnie po normalizacji.
        """

        norm_query = normalize_text(query)
        if len(norm_query) < 3:
            return []
        matches: list[str] = []
        for item in known_items:
            norm_item = normalize_text(item)
            if len(norm_item) < 3:
                continue
            if norm_item in norm_query:
                matches.append(item)
        # Preferujemy najdłuższe dopasowanie, aby uniknąć duplikatów typu warianty rezystora.
        matches = sorted(unique_preserve_order(matches), key=lambda value: len(normalize_text(value)), reverse=True)
        return matches[:1]

    def _best_item_by_query_score(self, query: str, known_items: list[str]) -> str | None:
        """Wybiera najlepszy pojedynczy przedmiot na podstawie score dopasowania.

        Args:
            query: Treść zapytania.
            known_items: Lista znanych przedmiotów.

        Returns:
            Najlepiej dopasowany przedmiot lub `None`.
        """

        norm_query = normalize_text(query)
        if len(norm_query) < 3:
            return None

        query_tokens = [token for token in norm_query.split() if len(token) >= 2]
        if not query_tokens:
            return None
        query_stems = {self._stem_pl(token) for token in query_tokens}

        best_item: str | None = None
        best_score: float = 0.0
        for item in known_items:
            norm_item = normalize_text(item)
            item_tokens = [token for token in norm_item.split() if len(token) >= 2]
            if not item_tokens:
                continue
            item_stems = {self._stem_pl(token) for token in item_tokens}
            overlap = len(query_stems & item_stems)
            token_ratio = overlap / max(1, len(item_stems))

            score = token_ratio
            if norm_item in norm_query:
                score += 1.5
            if any(token.isdigit() for token in query_tokens):
                numeric_hits = sum(1 for token in query_tokens if token.isdigit() and token in item_tokens)
                score += 0.3 * numeric_hits
            if re.search(r"\b\d+[a-z]+\b", norm_query):
                compact_hits = sum(1 for token in query_tokens if token in norm_item)
                score += 0.08 * compact_hits

            if score > best_score:
                best_score = score
                best_item = item

        if best_item is None:
            return None
        if best_score < 0.34:
            return None
        return best_item

    def _extract_from_json_like(self, query: str) -> list[str]:
        """Próbuje odczytać przedmioty z wejścia przypominającego JSON.

        Args:
            query: Surowa treść zapytania.

        Returns:
            Lista przedmiotów odczytana z pola `items` lub `item`.
        """

        text = query.strip()
        if not text.startswith("{"):
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return []

        raw_items = payload.get("items")
        if isinstance(raw_items, list):
            return [str(item) for item in raw_items if str(item).strip()]
        raw_item = payload.get("item")
        if isinstance(raw_item, str) and raw_item.strip():
            return [raw_item]
        return []

    def _extract_candidate_terms(self, query: str) -> list[str]:
        """Wyciąga kandydatów nazw przedmiotów z tekstu.

        Args:
            query: Treść zapytania.

        Returns:
            Lista kandydatów do dopasowania.
        """

        cleaned = query.strip()
        separators_pattern = r"[,\n;|]"
        parts = [part.strip() for part in re.split(separators_pattern, cleaned) if part.strip()]

        tokens = re.findall(r"\w+", cleaned.lower(), flags=re.UNICODE)
        stopwords = {
            "szukam",
            "potrzebuje",
            "potrzebujemy",
            "chce",
            "chcemy",
            "prosze",
            "mi",
            "nam",
            "oraz",
            "i",
            "lub",
            "dla",
            "do",
            "z",
            "na",
            "w",
            "miasto",
            "miasta",
        }
        tokens = [token for token in tokens if token not in stopwords and len(token) >= 2]
        bigrams = [" ".join(tokens[idx : idx + 2]) for idx in range(max(0, len(tokens) - 1))]
        trigrams = [" ".join(tokens[idx : idx + 3]) for idx in range(max(0, len(tokens) - 2))]

        return unique_preserve_order(parts + trigrams + bigrams + tokens)

    def _resolve_terms(self, terms: list[str], known_items: list[str]) -> list[str]:
        """Dopasowuje kandydatów do najbliższych znanych nazw przedmiotów.

        Args:
            terms: Kandydaci wyciągnięci z zapytania.
            known_items: Lista znanych nazw przedmiotów.

        Returns:
            Lista dopasowanych nazw przedmiotów.
        """

        if not known_items:
            return []
        known_norm = {normalize_text(item): item for item in known_items}
        known_stems = {self._stem_pl(norm): norm for norm in known_norm}
        known_token_stems: dict[str, str] = {}
        for norm_item in known_norm:
            for token in norm_item.split():
                stem = self._stem_pl(token)
                if len(stem) >= 3 and stem not in known_token_stems:
                    known_token_stems[stem] = norm_item
        resolved: list[str] = []

        for term in terms:
            norm_term = normalize_text(term)
            if len(norm_term) < 3:
                continue
            stem_term = self._stem_pl(norm_term)
            if norm_term in known_norm:
                resolved.append(known_norm[norm_term])
                continue
            if stem_term in known_stems:
                resolved.append(known_norm[known_stems[stem_term]])
                continue
            if stem_term in known_token_stems and len(stem_term) >= 4:
                resolved.append(known_norm[known_token_stems[stem_term]])
                continue

            best_local: str | None = None

            # Dopasowanie po zawieraniu całej frazy.
            for norm_item, original_item in known_norm.items():
                if (
                    norm_term in norm_item
                    or norm_item in norm_term
                    or stem_term in self._stem_pl(norm_item)
                ):
                    best_local = original_item
                    break

            if best_local:
                resolved.append(best_local)
                continue

            # Fuzzy fallback.
            best = difflib.get_close_matches(norm_term, list(known_norm.keys()), n=1, cutoff=0.78)
            if not best and len(stem_term) >= 4:
                stem_candidates = {self._stem_pl(key): key for key in known_norm}
                stem_best = difflib.get_close_matches(stem_term, list(stem_candidates.keys()), n=1, cutoff=0.72)
                if stem_best:
                    best = [stem_candidates[stem_best[0]]]
            if best:
                resolved.append(known_norm[best[0]])

        return unique_preserve_order(resolved)

    def _stem_pl(self, value: str) -> str:
        """Wykonuje prosty heurystyczny stemming dla polskich odmian rzeczowników.

        Args:
            value: Znormalizowany tekst wejściowy.

        Returns:
            Uproszczona postać słowa/frazy pomocna przy dopasowaniach fleksyjnych.
        """

        tokens = value.split()
        stemmed: list[str] = []
        suffixes = (
            "ami",
            "owie",
            "owie",
            "owego",
            "owej",
            "ego",
            "ach",
            "owie",
            "owie",
            "ow",
            "ow",
            "ie",
            "a",
            "u",
            "i",
            "y",
            "e",
        )
        for token in tokens:
            stem = token
            for suffix in suffixes:
                if len(stem) > 4 and stem.endswith(suffix):
                    stem = stem[: -len(suffix)]
                    break
            stemmed.append(stem)
        return " ".join(stemmed).strip()
