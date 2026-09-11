# S05E02 — Zestaw narzędzi

Źródło: `s05e02-zestaw-narzedzi-1775625284.md`

## Cel lekcji
- Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.

## Kluczowe obszary
- Film do lekcji
- Budowanie interfejsu użytkownika
- Przydatne narzędzia dla agentów
- Silniki wyszukiwania i bazy wektorowe
- Własne rozwiązania i narzędzia
- Fabuła
- Transkrypcja filmu z Fabułą
- Zadanie praktyczne

## Zasady implementacyjne dla agentów
- Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja).
- Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku.
- Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn.
- Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection.
- Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.

## Checklist wykonania zadania
- [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne?
- [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń?
- [ ] Czy dane wejściowe są walidowane?
- [ ] Czy wynik ma stabilny format?
- [ ] Czy istnieje fallback na błędy modelu/API?
- [ ] Czy dodano test(y) dla ścieżek krytycznych?

## Antywzorce
- Przeciążanie kontekstu nieistotnymi danymi.
- Brak walidacji outputu modelu przed użyciem w logice.
- Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej.
- Brak obserwowalności (logów decyzji i wywołań narzędzi).

## Szablon promptu startowego
`	ext
Kontekst lekcji: S05E02 — Zestaw narzędzi
Cel zadania: {CEL}
Ograniczenia: {OGRANICZENIA}
Narzędzia: {NARZĘDZIA}
Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte.
`"
  # S05E02 — Zestaw narzędzi  Źródło: `s05e02-zestaw-narzedzi-1775625284.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Film do lekcji - Budowanie interfejsu użytkownika - Przydatne narzędzia dla agentów - Silniki wyszukiwania i bazy wektorowe - Własne rozwiązania i narzędzia - Fabuła - Transkrypcja filmu z Fabułą - Zadanie praktyczne  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: S05E02 — Zestaw narzędzi Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += "
  # S05E02 — Zestaw narzędzi  Źródło: `s05e02-zestaw-narzedzi-1775625284.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Film do lekcji - Budowanie interfejsu użytkownika - Przydatne narzędzia dla agentów - Silniki wyszukiwania i bazy wektorowe - Własne rozwiązania i narzędzia - Fabuła - Transkrypcja filmu z Fabułą - Zadanie praktyczne  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: S05E02 — Zestaw narzędzi Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += 
-
