# Techniki łączenia modelu z narzędziami

Źródło: `s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164.md`

## Cel lekcji
- Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.

## Kluczowe obszary
- Zasady łączenia modelu językowego z narzędziami
- Function Calling oraz natywne oraz własne narzędzia
- Dobre praktyki opisywania schematów i ich właściwości
- Ustalanie domyślnych wartości, walidacji oraz zabezpieczeń
- Połączenie modelu z usługami przez API, proxy oraz CLI
- Personalizacja narzędzi dzięki Augmented Function Calling
- Zasady projektowania workflow oraz logiki agentów
- Refleksja oraz interpretacja zapytań w dynamicznym kontekście
- Transformacja oraz wzbogacanie zapytań przez LLM
- Techniki optymalizacji szybkości i skuteczności narzędzi
- Podstawy zarządzania kontekstem w workflow i logice agentów
- Dynamiczne listy narzędzi i zasobów wiedzy
- Obsługa wymaganych danych wejściowych, uprawnień oraz zgody
- Rola problemu prompt injection oraz jailbreakingu
- Fabuła
- Transkrypcja filmu z Fabułą
- Zadanie

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
Kontekst lekcji: Techniki łączenia modelu z narzędziami
Cel zadania: {CEL}
Ograniczenia: {OGRANICZENIA}
Narzędzia: {NARZĘDZIA}
Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte.
`"
  # Techniki łączenia modelu z narzędziami  Źródło: `s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Zasady łączenia modelu językowego z narzędziami - Function Calling oraz natywne oraz własne narzędzia - Dobre praktyki opisywania schematów i ich właściwości - Ustalanie domyślnych wartości, walidacji oraz zabezpieczeń - Połączenie modelu z usługami przez API, proxy oraz CLI - Personalizacja narzędzi dzięki Augmented Function Calling - Zasady projektowania workflow oraz logiki agentów - Refleksja oraz interpretacja zapytań w dynamicznym kontekście - Transformacja oraz wzbogacanie zapytań przez LLM - Techniki optymalizacji szybkości i skuteczności narzędzi - Podstawy zarządzania kontekstem w workflow i logice agentów - Dynamiczne listy narzędzi i zasobów wiedzy - Obsługa wymaganych danych wejściowych, uprawnień oraz zgody - Rola problemu prompt injection oraz jailbreakingu - Fabuła - Transkrypcja filmu z Fabułą - Zadanie  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: Techniki łączenia modelu z narzędziami Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += "
  # Techniki łączenia modelu z narzędziami  Źródło: `s01e02-techniki-laczenia-modelu-z-narzedziami-1773132164.md`  ## Cel lekcji - Zrozumieć i zastosować temat lekcji w implementacji agentów i kodu produkcyjnego.  ## Kluczowe obszary - Zasady łączenia modelu językowego z narzędziami - Function Calling oraz natywne oraz własne narzędzia - Dobre praktyki opisywania schematów i ich właściwości - Ustalanie domyślnych wartości, walidacji oraz zabezpieczeń - Połączenie modelu z usługami przez API, proxy oraz CLI - Personalizacja narzędzi dzięki Augmented Function Calling - Zasady projektowania workflow oraz logiki agentów - Refleksja oraz interpretacja zapytań w dynamicznym kontekście - Transformacja oraz wzbogacanie zapytań przez LLM - Techniki optymalizacji szybkości i skuteczności narzędzi - Podstawy zarządzania kontekstem w workflow i logice agentów - Dynamiczne listy narzędzi i zasobów wiedzy - Obsługa wymaganych danych wejściowych, uprawnień oraz zgody - Rola problemu prompt injection oraz jailbreakingu - Fabuła - Transkrypcja filmu z Fabułą - Zadanie  ## Zasady implementacyjne dla agentów - Definiuj jawny kontrakt wejścia i wyjścia (schema + walidacja). - Ograniczaj kontekst do sygnału potrzebnego dla bieżącego kroku. - Obsługuj błędy narzędzi i modeli przez retry, fallback i logowanie przyczyn. - Wymuszaj bezpieczeństwo: minimalne uprawnienia, kontrola źródeł, odporność na injection. - Dodawaj mierzalne kryteria sukcesu i test regresji dla kluczowego workflow.  ## Checklist wykonania zadania - [ ] Czy wymagania funkcjonalne są jednoznaczne i mierzalne? - [ ] Czy agent ma właściwy zestaw narzędzi i ograniczeń? - [ ] Czy dane wejściowe są walidowane? - [ ] Czy wynik ma stabilny format? - [ ] Czy istnieje fallback na błędy modelu/API? - [ ] Czy dodano test(y) dla ścieżek krytycznych?  ## Antywzorce - Przeciążanie kontekstu nieistotnymi danymi. - Brak walidacji outputu modelu przed użyciem w logice. - Łączenie decyzji krytycznych wyłącznie z odpowiedzią LLM bez kontroli deterministycznej. - Brak obserwowalności (logów decyzji i wywołań narzędzi).  ## Szablon promptu startowego `	ext Kontekst lekcji: Techniki łączenia modelu z narzędziami Cel zadania: {CEL} Ograniczenia: {OGRANICZENIA} Narzędzia: {NARZĘDZIA} Zwróć: plan + implementację + testy + ryzyka + decyzje otwarte. += 
-
