# lesson4_mailboc

Pobieranie przykładowych maili z API `zmail` i zapis na dysku.

## Uruchomienie

```powershell
python Season2/lesson4_mailboc/fetch_sample_mails.py --query "from:proton.me" --max-messages 8
```

## Wynik

Skrypt zapisuje pliki w:

`Season2/lesson4_mailboc/output/<YYYYMMDD_HHMMSS>/`

- `help.json`
- `inbox_page1.json`
- `search.json`
- `message_*.json`
- `sample_messages.json`
