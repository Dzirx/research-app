# AI Creator Intelligence Report

Codzienny raport PDF dla twórców contentu AI. Scrape'uje Instagram, Facebook i newslettery RSS, analizuje trendy i wysyła gotowy raport na e-mail.

---

## Wymagania

- Python 3.12+
- Docker (do uruchomienia PostgreSQL)
- Konto [Apify](https://apify.com) (~$0.30/mies. przy codziennym uruchomieniu)
- Klucz API [OpenAI](https://platform.openai.com)
- Klucz API [Anthropic](https://console.anthropic.com)
- VPS Mikrus

---

## Instalacja

### 1. Skopiuj projekt na VPS

```bash
cd ~
git clone <repo> ai-creator-report
cd ai-creator-report
```

### 2. Uruchom bazę danych

```bash
docker compose up -d
```

PostgreSQL startuje na porcie `5432`, tabele tworzone są automatycznie ze skryptu `db/schema.sql`.

### 3. Utwórz virtualenv i zainstaluj zależności

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 4. Skonfiguruj zmienne środowiskowe

```bash
cp .env.example .env
nano .env
```

Wypełnij wszystkie wartości:

```env
DATABASE_URL=postgresql://user:password@localhost:5432/ai_report

OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
APIFY_TOKEN=apify_api_...

SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=twoj@gmail.com
SMTP_PASS=haslo_aplikacji_gmail

REPORT_RECIPIENT=klient@gmail.com
REPORT_OUTPUT_DIR=/home/twoj_user/reports
```

> **Gmail SMTP:** wejdź na myaccount.google.com → Bezpieczeństwo → Hasła do aplikacji → wygeneruj hasło dla "Poczta".

### 5. Dodaj konta do śledzenia

Edytuj `accounts.yaml` i wpisz konta Instagram, Facebook i RSS które chcesz śledzić:

```yaml
instagram:
  - url: https://www.instagram.com/nazwa_konta/
    label: Nazwa Konta

facebook:
  - url: https://www.facebook.com/nazwa.strony
    label: Nazwa Strony

rss:
  - url: https://tldr.tech/ai/rss
    label: TLDR AI
```

---

## Uruchomienie

### Test ręczny (pierwsze uruchomienie)

```bash
source .venv/bin/activate
python main.py
```

Sprawdź czy PDF pojawił się w `REPORT_OUTPUT_DIR` i czy dotarł e-mail.

### Uruchomienie tylko wybranego kroku (debug)

```bash
# Tylko scraping social media
python -m scrapers.social

# Tylko RSS
python -m scrapers.rss

# Tylko analiza trendów
python -m processing.analyze

# Tylko generowanie PDF
python -m report.generate
```

### Automatyczne uruchamianie (Cron)

```bash
crontab -e
```

Wklej linię (podmień ścieżki):

```
30 4 * * * cd /home/twoj_user/ai-creator-report && .venv/bin/python main.py >> /home/twoj_user/logs/report.log 2>&1
```

Utwórz folder na logi:

```bash
mkdir -p ~/logs
```

Sprawdź czy cron działa:

```bash
crontab -l
```

---

## Struktura projektu

```
ai-creator-report/
├── accounts.yaml          # lista kont do śledzenia (edytuj to)
├── docker-compose.yml     # PostgreSQL kontener
├── main.py                # orchestrator — odpala cały pipeline
├── send.py                # wysyłka e-mail
├── requirements.txt
├── .env.example           # szablon zmiennych środowiskowych
├── crontab.txt            # gotowa linia do wklejenia w crontab
│
├── scrapers/
│   ├── social.py          # Apify: Instagram + Facebook
│   └── rss.py             # newslettery i blogi przez RSS
│
├── processing/
│   ├── transcribe.py      # OpenAI Whisper — transkrypcja Reels
│   ├── analyze.py         # GPT-4o mini — summaries + trendy
│   ├── enrich_articles.py # GPT-4o mini — artykuły → bullet-pointy PL
│   └── verify.py          # Claude Sonnet 4.6 — fact-check i hype detection
│
├── report/
│   ├── generate.py        # Jinja2 + Playwright → PDF
│   └── templates/
│       └── report.html    # szablon PDF
│
└── db/
    ├── schema.sql         # schemat bazy (uruchamiany automatycznie przez Docker)
    └── queries.py         # funkcje do bazy danych
```

---

## Sekcje raportu PDF

| # | Sekcja | Opis |
|---|--------|------|
| I | Dziennik AI Social | Wszystkie posty z IG/FB z ostatnich 24h |
| II | Radar Nowości AI | Trendy: 🚀 breaking / 📈 trending / 🔄 recurring / 📉 fading |
| III | Top 3 posty | Najwyższy engagement + analiza dlaczego viral |
| IV | Newslettery & Blogi | Bullet-pointy po polsku z RSS |
| V | Skrypty Wideo | 3 gotowe hook + body + CTA do nagrania |
| VI | Baza Hooków | Najlepsze hooki z wyjaśnieniem mechanizmu |

---

## Koszt jednego uruchomienia (zmierzony)

| Usługa | Koszt |
|--------|-------|
| Apify (instagram-post-scraper) | ~$0.01 |
| OpenAI (Whisper + GPT-4o mini) | ~$0.02 |
| Claude Sonnet 4.6 (verify) | ~$0.01 |
| **Razem / dzień** | **~$0.04** |
| **Razem / miesiąc** | **~$1.20** |

> Pomiar przy 3 postach z Instagrama. Przy większej liczbie kont i postów koszt wzrośnie liniowo.

## Szacowany koszt miesięczny (z VPS)

| Usługa | Koszt |
|--------|-------|
| Mikrus VPS | ~15 PLN |
| API (Apify + OpenAI + Claude) | ~5 PLN |
| **Razem** | **~20 PLN/mies.** |
