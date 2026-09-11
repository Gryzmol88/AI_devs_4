# lesson5_limits

Prosty klient do zadania `railway` z:
- retry dla `429`, `503` i `5xx`,
- backoffem wykładniczym + jitter,
- odczytem nagłówków limitów (`Retry-After`, `X-RateLimit-*`, `RateLimit-*`),
- modelami `pydantic` dla konfiguracji i payloadu.

## Uruchomienie

Ustaw klucz API w `.env` albo w środowisku:
- `HUB_API_KEY=...` (preferowane) lub
- `API_KEY=...`

Następnie uruchom:

```bash
python lesson5_limits/main.py
```

Skrypt wykona sekwencję:
1. `help`
2. `getstatus`
3. `reconfigure`
4. `setstatus` (`RTOPEN`)
5. `save`
6. `getstatus`

Dla wariantów trasy `X-01` i `x-01`.

## Wynik

Ostatnia odpowiedź API jest zapisywana do:

`lesson5_limits/output/verify_response.json`
