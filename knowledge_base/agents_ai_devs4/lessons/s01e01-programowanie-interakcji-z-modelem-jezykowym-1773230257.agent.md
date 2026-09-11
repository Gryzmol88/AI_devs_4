# Programowanie interakcji z modelem językowym

Źródło: `s01e01-programowanie-interakcji-z-modelem-jezykowym-1773230257.md`

## Cel lekcji
- Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.

## Kluczowe obszary
- Sterowanie zachowaniem modelu z pomocą kodu
- Strukturyzowanie odpowiedzi oraz JSON Schema
- Formatowanie i renderowanie odpowiedzi LLM oraz LRM
- Różnice pomiędzy interfejsem użytkownika, a logiką aplikacji
- Strategie wyboru dużych i mniejszych modeli w praktyce
- Najważniejsze natywne funkcjonalności API głównych providerów
- Najnowsze techniki organizowania instrukcji w kodzie aplikacji
- Generowanie instrukcji i techniki optymalizacji z pomocą LLM
- Specjalizowanie zachowania modeli poprzez kontekst, few-shot oraz many-shot
- Structured Outputs w praktyce
- Przykłady struktur baz danych dla czatbotów i agentów
- Bieżący stan modeli open-source z LM Studio, ich możliwości oraz wymagania sprzętowe i przydatne opcje konfiguracji
- Aktualne źródła wiedzy, profile, narzędzia i usługi, które warto znać
- Fabuła
- Transkrypcja filmu z Fabułą
- Jak działają zadania w kursie
- Zadanie
- Linki do filmu Mateusza

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
Kontekst lekcji: Programowanie interakcji z modelem językowym
Cel zadania: {CEL}
Ograniczenia: {OGRANICZENIA}
Narzędzia: {NARZĘDZIA}
Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte.
`"
  # Programowanie interakcji z modelem językowym  Źródło: `s01e01-programowanie-interakcji-z-modelem-jezykowym-1773230257.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Sterowanie zachowaniem modelu z pomocą kodu - Strukturyzowanie odpowiedzi oraz JSON Schema - Formatowanie i renderowanie odpowiedzi LLM oraz LRM - Różnice pomiędzy interfejsem użytkownika, a logiką aplikacji - Strategie wyboru dużych i mniejszych modeli w praktyce - Najważniejsze natywne funkcjonalności API głównych providerów - Najnowsze techniki organizowania instrukcji w kodzie aplikacji - Generowanie instrukcji i techniki optymalizacji z pomocą LLM - Specjalizowanie zachowania modeli poprzez kontekst, few-shot oraz many-shot - Structured Outputs w praktyce - Przykłady struktur baz danych dla czatbotów i agentów - Bieżący stan modeli open-source z LM Studio, ich możliwości oraz wymagania sprzętowe i przydatne opcje konfiguracji - Aktualne źródła wiedzy, profile, narzędzia i usługi, które warto znać - Fabuła - Transkrypcja filmu z Fabułą - Jak działają zadania w kursie - Zadanie - Linki do filmu Mateusza  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: Programowanie interakcji z modelem językowym Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += "
  # Programowanie interakcji z modelem językowym  Źródło: `s01e01-programowanie-interakcji-z-modelem-jezykowym-1773230257.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Sterowanie zachowaniem modelu z pomocą kodu - Strukturyzowanie odpowiedzi oraz JSON Schema - Formatowanie i renderowanie odpowiedzi LLM oraz LRM - Różnice pomiędzy interfejsem użytkownika, a logiką aplikacji - Strategie wyboru dużych i mniejszych modeli w praktyce - Najważniejsze natywne funkcjonalności API głównych providerów - Najnowsze techniki organizowania instrukcji w kodzie aplikacji - Generowanie instrukcji i techniki optymalizacji z pomocą LLM - Specjalizowanie zachowania modeli poprzez kontekst, few-shot oraz many-shot - Structured Outputs w praktyce - Przykłady struktur baz danych dla czatbotów i agentów - Bieżący stan modeli open-source z LM Studio, ich możliwości oraz wymagania sprzętowe i przydatne opcje konfiguracji - Aktualne źródła wiedzy, profile, narzędzia i usługi, które warto znać - Fabuła - Transkrypcja filmu z Fabułą - Jak działają zadania w kursie - Zadanie - Linki do filmu Mateusza  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: Programowanie interakcji z modelem językowym Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += 
-
