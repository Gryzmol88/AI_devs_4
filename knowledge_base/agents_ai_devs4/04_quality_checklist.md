# Checklista jakości przed oddaniem

## Poprawność
- [ ] Czy wynik spełnia wymagania funkcjonalne?
- [ ] Czy obsłużono edge-case'y i stany błędu?
- [ ] Czy output ma stabilny format (np. JSON schema)?

## Bezpieczeństwo
- [ ] Czy wejście jest walidowane?
- [ ] Czy narzędzia mają minimalne wymagane uprawnienia?
- [ ] Czy ograniczono ryzyko prompt injection?

## Kontekst i architektura
- [ ] Czy kontekst jest minimalny i trafny?
- [ ] Czy pamięć/stany są aktualizowane jawnie?
- [ ] Czy podział ról agentów jest spójny?

## Operacyjność
- [ ] Czy są logi decyzji i wywołań narzędzi?
- [ ] Czy zdefiniowano retry/fallback/timeout?
- [ ] Czy koszt i latencja są akceptowalne?

## Testy i ewaluacja
- [ ] Czy testy pokrywają ścieżki krytyczne?
- [ ] Czy istnieje test regresji promptów/workflow?
- [ ] Czy metryki sukcesu są mierzalne?
