# AI Creator Intelligence Report

Codzienny raport PDF z researchu contentu AI na Instagramie/Facebooku — analizuje trendy i wysyła gotowy raport na e-mail.

---

## Wymagania

- Python 3.12+
- Konto [Apify](https://apify.com) (~$0.30/mies. przy codziennym uruchomieniu)
- Klucz API [OpenAI](https://platform.openai.com)
- Klucz API [Anthropic](https://console.anthropic.com)
- VPS Mikrus

Baza danych to plik SQLite — nie ma osobnego serwera bazy do uruchamiania, plik tworzy się
automatycznie przy pierwszym połączeniu.

---

## Instalacja

### 1. Skopiuj projekt na VPS

```bash
cd ~
git clone <repo> ai-creator-report
cd ai-creator-report
```

### 2. Utwórz virtualenv i zainstaluj zależności

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. Skonfiguruj zmienne środowiskowe

```bash
cp .env.example .env
nano .env
```

Wypełnij wszystkie wartości:

```env
DATABASE_PATH=./db/research.sqlite3

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

### 4. Dodaj konta do śledzenia

Edytuj `accounts.yaml` i wpisz konta Instagram (opcjonalnie Facebook), które chcesz śledzić,
oraz swoje własne konto (`own_account`) — służy tylko do wykrywania, które zaproponowane
pomysły na rolkę faktycznie opublikowałeś:

```yaml
instagram:
  - url: https://www.instagram.com/nazwa_konta/
    label: Nazwa Konta

own_account:
  - url: https://www.instagram.com/twoje_konto/
    label: Twoje Imię

facebook:
  - url: https://www.facebook.com/nazwa.strony
    label: Nazwa Strony
```

### 5. Dostosuj profil marki

Edytuj `brand_profile.yaml` — temat, styl, projekty, zasady CTA. Ten plik jest wstrzykiwany
do promptu generującego skrypty wideo (sekcja IV raportu), więc im dokładniejszy, tym
bardziej trafione skrypty.

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
# Tylko scraping social media (+ własne konto)
python -m scrapers.social

# Tylko analiza trendów
python -m processing.analyze

# Tylko sprawdzenie, które pomysły na rolkę już opublikowałeś
python -m processing.check_published

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
├── accounts.yaml          # lista kont do śledzenia + Twoje własne konto (edytuj to)
├── brand_profile.yaml     # temat, styl, CTA — wstrzykiwane do promptu skryptów wideo
├── main.py                # orchestrator — odpala cały pipeline
├── send.py                # wysyłka e-mail
├── requirements.txt
├── .env.example           # szablon zmiennych środowiskowych
│
├── scrapers/
│   └── social.py          # Apify: Instagram + Facebook + własne konto
│
├── processing/
│   ├── transcribe.py      # OpenAI Whisper — transkrypcja Reels
│   ├── analyze.py         # GPT-4o mini — summaries + trendy
│   ├── check_published.py # GPT-4o mini — wykrywa, które pomysły już opublikowałeś
│   └── verify.py          # Claude Sonnet 4.6 — fact-check i hype detection
│
├── report/
│   ├── generate.py        # Jinja2 + Playwright → PDF, generuje i loguje skrypty wideo
│   └── templates/
│       └── report.html    # szablon PDF
│
└── db/
    ├── schema.sql         # schemat bazy (uruchamiany automatycznie przy każdym połączeniu)
    ├── queries.py          # funkcje do bazy danych (SQLite)
    └── research.sqlite3   # plik bazy — tworzy się sam, nie w gicie
```

---

## Sekcje raportu PDF

| # | Sekcja | Opis |
|---|--------|------|
| I | Dziennik AI Social | Wszystkie posty z IG/FB z ostatnich 24h |
| II | Radar Nowości AI | Trendy: 🚀 breaking / 📈 trending / 🔄 recurring / 📉 fading |
| III | Top 3 posty | Najwyższy engagement + analiza dlaczego viral |
| IV | Skrypty Wideo | 3 gotowe hook + body + CTA do nagrania, dopasowane do `brand_profile.yaml` i bez powtórek (patrz `script_ideas` / `own_posts`) |
| V | Baza Hooków | Najlepsze hooki z wyjaśnieniem mechanizmu |

---

## Koszt jednego uruchomienia (zmierzony)

| Usługa | Koszt |
|--------|-------|
| Apify (instagram-post-scraper) | ~$0.01 |
| OpenAI (Whisper + GPT-4o mini: analiza/OCR) | ~$0.02 |
| OpenAI (gpt-5.6-sol: generowanie skryptów wideo) | ~$0.02–0.05 |
| Claude Sonnet 4.6 (verify) | ~$0.01 |
| **Razem / dzień** | **~$0.05–0.08** |
| **Razem / miesiąc** | **~$1.50–2.40** |

> Pomiar przy 3 postach z Instagrama. Przy większej liczbie kont i postów koszt wzrośnie liniowo.
> Koszt GPT-5 to szacunek — jedno wywołanie dziennie, dokładna cena zależy od aktualnego cennika OpenAI.

## Szacowany koszt miesięczny (z VPS)

| Usługa | Koszt |
|--------|-------|
| Mikrus VPS | ~15 PLN |
| API (Apify + OpenAI + Claude) | ~5 PLN |
| **Razem** | **~20 PLN/mies.** |
