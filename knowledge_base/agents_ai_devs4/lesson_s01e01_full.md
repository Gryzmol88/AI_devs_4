# S01E01 - Programowanie interakcji z modelem językowym

Źródło: `s01e01-programowanie-interakcji-z-modelem-jezykowym-1773230257.md`

## Cel
- Zbudować poprawną i przewidywalną integrację aplikacji z LLM przez API.
- Rozdzielić logikę deterministyczną (kod) od niedeterministycznej (model).
- Wymusić ustrukturyzowane odpowiedzi, które da się bezpiecznie przetwarzać.

## Kluczowe pojęcia
- Token, okno kontekstowe, limit outputu.
- Prompt systemowy i jego rola w sterowaniu zachowaniem.
- Structured output / JSON Schema.
- Różnica UI czatu vs logika produkcyjna backendu.
- Dobór modelu do zadania (jakość, koszt, latency).

## Zasady implementacyjne
- Wymagaj formatu odpowiedzi przez schema i walidację po stronie aplikacji.
- Nie używaj surowej odpowiedzi LLM bez walidacji i normalizacji.
- Utrzymuj krótki, celowy kontekst; usuwaj dane nieistotne dla bieżącego kroku.
- Dodaj fallback: retry, model zapasowy, odpowiedź awaryjna.
- Loguj request/response metadane (bez wrażliwych danych).

## Minimalny workflow produkcyjny
1. Zbierz input użytkownika.
2. Zbuduj prompt systemowy + kontekst zadania.
3. Wywołaj model z limitem tokenów i wymuszonym formatem.
4. Zwaliduj odpowiedź schema validator.
5. W razie błędu: retry lub fallback.
6. Zwróć wynik do UI + zapisz log diagnostyczny.

## Kontrakt danych (przykład)
```json
{
  "type": "object",
  "properties": {
    "result": { "type": "string" },
    "confidence": { "type": "number", "minimum": 0, "maximum": 1 },
    "needs_human_review": { "type": "boolean" }
  },
  "required": ["result", "confidence", "needs_human_review"],
  "additionalProperties": false
}
```

## Checklist przed oddaniem
- [ ] Odpowiedź modelu jest walidowana przez JSON Schema.
- [ ] Krytyczne decyzje nie opierają się wyłącznie na LLM.
- [ ] Obsłużono limity tokenów i błędy API.
- [ ] Dodano logi diagnostyczne i metryki jakości.
- [ ] Są testy dla poprawnej i błędnej odpowiedzi modelu.

## Antywzorce
- Parsowanie odpowiedzi „na stringach” bez kontraktu.
- Wrzucanie całej historii rozmowy do każdego requestu.
- Brak timeoutów i brak fallbacku.
- Mieszanie promptów UI z logiką backendową.

## Prompt startowy dla agenta kodującego
```text
Kontekst: S01E01 - Programowanie interakcji z modelem językowym.
Cel: zaimplementuj endpoint integrujący LLM z walidacją JSON Schema.
Wymagania:
- structured output
- timeout + retry
- fallback na błąd API
- testy jednostkowe walidacji
Zwróć:
1) plan
2) zmiany w kodzie
3) testy
4) ryzyka i ograniczenia
```
