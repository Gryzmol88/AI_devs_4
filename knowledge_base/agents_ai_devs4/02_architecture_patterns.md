# Wzorce architektury dla agentów

## A) Single Agent + Tools
- Używaj dla prostych, liniowych zadań.
- Agent: planuje i wywołuje narzędzia.
- Wymagane: walidacja outputu i retry policy.

## B) Manager + Specialist Agents
- Używaj dla zadań z różnymi kompetencjami.
- Manager: dekompozycja zadania i scalenie wyników.
- Specjaliści: np. `research`, `coder`, `reviewer`, `tester`.

## C) Retrieval-First Agent (RAG)
- Używaj gdy wiedza pochodzi z dokumentów.
- Kroki: indeksowanie -> retrieval -> synteza -> cytowanie źródeł.
- Wymagane: ranking trafności i limit kontekstu.

## D) Event-Driven Agent Loop
- Używaj dla procesów asynchronicznych i dłuższych workflow.
- Agent reaguje na zdarzenia i aktualizuje stan.
- Wymagane: trwały stan, idempotencja, audyt zdarzeń.

## E) Human-in-the-Loop
- Używaj przy wysokim ryzyku błędu.
- Agent prosi o akceptację przed akcjami krytycznymi.
- Wymagane: czytelna prezentacja ryzyka i opcji decyzji.
