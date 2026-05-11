# Race Report Dashboard

Automated monthly Global Races Report — beautiful web dashboard, downloadable Excel
matching the existing format, data sourced **only** from each race's official site.

## Run it

```powershell
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765/

## What's there

- **Dashboard** — 70 shortlisted 2026 races, KPIs, charts, filters (month/country/label/category/search), grid + timeline views.
- **Monthly report generator** — `POST /api/reports/generate?month=YYYY-MM` builds the
  4-sheet Excel (Race Overview / Elite Results / Sponsorship & Partnerships / Events' Highlights).
- **Scheduler** — runs on the 1st of each month at 09:00 local, generates the prior month.
- **Per-race scrapers** — pluggable, official-URL-only enforcement at the base class.

## Project layout

```
app/
  data.py             # XLSX → Race objects
  excel_report.py     # 4-sheet Excel writer
  main.py             # FastAPI routes
  scheduler.py        # APScheduler monthly job
  scrapers/
    base.py           # BaseScraper + RaceFacts dataclass + official-URL guard
    registry.py       # race_id -> scraper class
    tokyo_marathon.py
    berliner_halbmarathon.py
    edp_lisbon_half.py
static/
  index.html          # single-page dashboard
  app.js              # Alpine + Chart.js
  styles.css
data/
  race_urls.json      # official URL per race
  reports/            # generated XLSX files
Shortlisted Races (2026).xlsx
Monthly Global Races Report_March 2026_14.04.2026.xlsx   # reference
```

## Adding a scraper for a new race

1. Create `app/scrapers/<race_slug>.py`.
2. Subclass `BaseScraper`, set `official_url`, decorate the class with
   `@register("<race-id>")` (the id is the slug used in `data/race_urls.json`).
3. Implement `scrape()` to return a `RaceFacts` object — fill whatever the
   official site exposes; missing fields are tolerated.
4. Import the new module in `app/scrapers/registry.py` so the decorator fires.

The base class **rejects any URL that's not on the official origin** so reports
can never accidentally include data from third-party aggregators.
