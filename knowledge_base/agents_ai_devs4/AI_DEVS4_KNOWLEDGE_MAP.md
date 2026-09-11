# AI_devs 4 - mapa wiedzy (skrót roboczy)

## S01 Fundamenty integracji LLM
- `s01e01`: podstawy interakcji z LLM przez API, tokeny i okno kontekstowe, structured outputs, dobór modeli, instrukcje systemowe, architektura czatów/agentów.
- `s01e02`: łączenie modelu z narzędziami (function calling), schematy wejścia/wyjścia, walidacje i zabezpieczenia, workflow agentowy, prompt injection i zgody/uprawnienia.
- `s01e03`: projektowanie API pod AI, MCP vs własne podejście, bezpieczeństwo i autoryzacja, skalowanie wielu narzędzi, konflikty między serwerami.
- `s01e04`: multimodalność (obraz/audio/wideo/PDF), iteracyjne generowanie i edycja, referencje wizualne, pipeline przetwarzania załączników.
- `s01e05`: limity jawne i ukryte, błędy modeli, ograniczenia środowiskowe, przygotowanie wdrożenia produkcyjnego.

## S02 Kontekst, RAG i agenci
- `s02e01`: zarządzanie kontekstem rozmowy, oddzielanie sygnału od szumu, dynamiczne instrukcje, kontrola stanu poza oknem kontekstu.
- `s02e02`: zewnętrzny kontekst (narzędzia/dokumenty), indeksowanie, retrieval, embeddingi, wyszukiwarki i bazy wektorowe, wyzwania jakości RAG.
- `s02e03`: dokumenty i pamięć długoterminowa jako narzędzia, mapowanie wiedzy, grafy, organizacja zasobów.
- `s02e04`: wielowątkowość i multi-agent, kontekst globalny, podział odpowiedzialności, koordynacja manager-agent.
- `s02e05`: projektowanie agentów: zakres odpowiedzialności, instrukcje, dobór narzędzi, wiedzy i ustawień.

## S03 Obserwowalność, ewaluacja i odporność
- `s03e01`: obserwowalność, monitoring, debugowanie stanu, wersjonowanie promptów, metryki i ewaluacja skuteczności.
- `s03e02`: ograniczenia modeli na etapie projektu, poziom trudności zadań, halucynacje, wydajność, redukcja ryzyka injection.
- `s03e03`: kontekstowy feedback z otoczenia, pętle informacji zwrotnej, wsparcie człowieka.
- `s03e04`: budowa narzędzi na danych testowych, datasety, automatyczna optymalizacja schematów/odpowiedzi, dobór modeli.
- `s03e05`: wykorzystanie niedeterminizmu jako przewagi, sterowanie rozumowaniem, elastyczna prezentacja danych, generatywne UI.

## S04 Wdrożenia i współpraca z AI
- `s04e01`: wdrożenia AI w realnych procesach, mapowanie procesów, szybkie testy założeń.
- `s04e02`: aktywna współpraca z AI, personalizacja, meta-prompty, zadania jednorazowe.
- `s04e03`: kontekstowa współpraca, projektowanie procesów tła, zarządzanie zdarzeniami i komunikacją.
- `s04e04`: projektowanie prywatnej bazy wiedzy (Markdown), granica baza wiedzy vs pamięć długoterminowa, edycja notatek z pomocą modeli.
- `s04e05`: rozwiązania wewnątrzfirmowe, prywatność danych, konsekwencje błędów, integracja z usługami i narzędziami organizacji.

## S05 Architektura, produkcja i rozwój
- `s05e01`: architektura rozwiązania (przegląd przekrojowy).
- `s05e02`: zestaw narzędzi: UI, wyszukiwarki, bazy wektorowe, narzędzia własne.
- `s05e03`: rozwój funkcjonalności: migracje modeli/API, zarządzanie rozwojem agentów, wnioski z wdrożeń.
- `s05e04`: produkcja: praktyka operacyjna, ogólne sugestie, scenariusz zadaniowy.
- `s05e05`: nowa rzeczywistość: konfiguracja, narzędzia, zastosowania, współpraca z agentem i rozwój projektu.

## Zasady nadrzędne (wniosek przekrojowy)
- Traktuj LLM jako niedeterministyczny komponent systemu deterministycznego.
- Projektuj pod obserwowalność, ewaluację i iteracyjne ulepszanie.
- Ograniczaj powierzchnię ryzyka: walidacja, uprawnienia, kontrola narzędzi i kontekstu.
- Rozdzielaj odpowiedzialności: instrukcje, pamięć, retrieval, wykonanie narzędzi.
- Buduj system tak, by działał przy błędach modelu, a nie tylko przy idealnych odpowiedziach.
