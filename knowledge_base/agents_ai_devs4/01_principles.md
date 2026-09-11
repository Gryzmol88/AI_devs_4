# Zasady nadrzędne (AI_devs4)

## 1) LLM jako komponent niedeterministyczny
- Zakładaj, że odpowiedzi mogą się różnić przy tych samych danych.
- Krytyczne decyzje opieraj o walidację i logikę deterministyczną.

## 2) Kontekst to zasób ograniczony
- Przekazuj tylko sygnał, usuwaj szum.
- Utrzymuj osobno: instrukcje, stan, wiedzę i wyniki narzędzi.

## 3) Narzędzia przez jawne kontrakty
- Każde narzędzie musi mieć czytelny schemat wejścia i wyjścia.
- Waliduj dane i obsługuj błędy w ustrukturyzowany sposób.

## 4) Bezpieczeństwo domyślnie
- Ograniczaj uprawnienia narzędzi.
- Traktuj wejście użytkownika i dokumenty jako potencjalnie niebezpieczne.
- Projektuj pod odporność na prompt injection.

## 5) Obserwowalność i ewaluacja
- Loguj: input, decyzje, wywołania narzędzi, output.
- Miej metryki jakości i testy regresji promptów.

## 6) Iteracyjność i feedback
- Projektuj pętle informacji zwrotnej z otoczenia i od człowieka.
- Ulepszaj system przez krótkie cykle test -> poprawa -> test.

## 7) Produkcyjna pragmatyka
- Zawsze definiuj fallback na błędy modelu/API/narzędzi.
- Dbaj o koszty, limity i opóźnienia.
