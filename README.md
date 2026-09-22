# AI Creator Intelligence Report

Codzienny raport PDF z researchu contentu AI na Instagramie/Facebooku — analizuje trendy i wysyła gotowy raport na e-mail.

---

## Wymagania

- Python 3.12+
- Konto [Apify](https://apify.com) (~$0.30/mies. przy codziennym uruchomieniu)
- Klucz API [OpenAI](https://platform.openai.com) — jedyny dostawca modeli w tym projekcie
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
# jak daleko wstecz sięga Apify; ten sam post nie trafi do raportu dwa razy (dedup po URL)
scrape_window: "3 days"

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

> **Gdy nie ma nowych postów** pipeline kończy się po scrapingu: PDF nie powstaje i mail nie
> leci. W logu zobaczysz `0 nowych postów — cisza w eterze`. Dzięki temu nie płacisz za
> generowanie raportu z niczego. Posty widziane wcześniej dostają tylko świeży
> `engagement_score` i nie są analizowane drugi raz.

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
│   └── check_published.py # GPT-4o mini — wykrywa, które pomysły już opublikowałeś
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

### Baza danych

`schema.sql` wykonuje się przy każdym połączeniu (`CREATE TABLE IF NOT EXISTS`), więc nowa baza
tworzy się sama. **Nie ma automatycznych migracji** — po zmianie schematu skasuj plik bazy:

```bash
rm db/research.sqlite3   # następne uruchomienie odtworzy schemat
```

Co gdzie leży:

| Tabela | Zawartość |
|--------|-----------|
| `posts` | caption, URL (UNIQUE — klucz deduplikacji), `scraped_at` = data pierwszego zobaczenia, `engagement_score` |
| `transcriptions` | transkrypcja rolki, jedna na post |
| `summaries` | `summary_pl`, `trend_tags`, `hook_type` oraz `key_points` — konkrety z materiału |
| `trend_clusters` | temat, status (breaking/trending/recurring/fading), liczba źródeł, engagement, delta vs 7 dni |
| `hooks` | hook, typ, dlaczego działa |
| `script_ideas` | zaproponowane skrypty + `source_url` i `source_note` (z czego wyrosły); `status` przechodzi na `published`, gdy pomysł pojawi się na Twoim koncie |
| `own_posts` | Twoje opublikowane posty — wyłącznie do wykrywania powtórek |
| `reports` | historia wygenerowanych PDF-ów |

---

## Sekcje raportu PDF

| # | Sekcja | Opis |
|---|--------|------|
| I | Dziennik AI Social | Posty z IG/FB zobaczone dziś po raz pierwszy |
| II | Radar Nowości AI | Rozdzielony na **potwierdzone trendy** (≥2 różne konta) i **pojedyncze sygnały** (1 konto). Status: breaking / trending / recurring / fading + zmiana engagementu vs ostatnie 7 dni |
| III | Top 3 posty | Najwyższy engagement + konkrety z materiału + analiza dlaczego viral |
| IV | Skrypty Wideo | 3 gotowe hook + body + CTA, każdy z linkiem do posta źródłowego i notką „na bazie" — widać, na czym skrypt stoi. Dopasowane do `brand_profile.yaml`, bez powtórek (patrz `script_ideas` / `own_posts`) |
| V | Baza Hooków | Najlepsze hooki z wyjaśnieniem mechanizmu |

### Skąd bierze się treść raportu

Rolki są transkrybowane Whisperem i to **transkrypcja jest źródłem merytoryki** — opis pod
postem (caption) to zwykle lead magnet („skomentuj AI, a wyślę szkolenie") i służy głównie do
wyciągnięcia hooka. Z transkrypcji powstają `summary_pl`, `trend_tags` oraz `key_points`
(2–5 konkretów, które realnie padły w materiale). Te konkrety idą potem do generatora skryptów —
bez nich model dostawałby samą nazwę tematu i dopisywał treść z głowy.
Post bez transkrypcji jest w raporcie oznaczony `[brak transkrypcji]`.

---

## Koszt jednego uruchomienia (zmierzony)

| Usługa | Koszt |
|--------|-------|
| Apify (instagram-post-scraper) | ~$0.01 |
| OpenAI (Whisper + GPT-4o mini: analiza/OCR) | ~$0.02 |
| OpenAI (gpt-5.6-sol: generowanie skryptów wideo) | ~$0.02–0.05 |
| **Razem / dzień** | **~$0.05–0.08** |
| **Razem / miesiąc** | **~$1.50–2.40** |

> Pomiar przy 3 postach z Instagrama. Przy większej liczbie kont i postów koszt wzrośnie liniowo.
> W dniu bez nowych postów płacisz wyłącznie za Apify — reszta pipeline'u się nie uruchamia.
> Koszt GPT-5 to szacunek — jedno wywołanie dziennie, dokładna cena zależy od aktualnego cennika OpenAI.

## Szacowany koszt miesięczny (z VPS)

| Usługa | Koszt |
|--------|-------|
| Mikrus VPS | ~15 PLN |
| API (Apify + OpenAI) | ~5 PLN |
| **Razem** | **~20 PLN/mies.** |
