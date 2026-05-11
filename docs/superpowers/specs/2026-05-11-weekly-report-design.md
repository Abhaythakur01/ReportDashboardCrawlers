# Weekly Report — design spec

**Status:** approved 2026-05-11
**Author:** Abhay (santosh.pillai@gmail.com) + Claude
**Type:** small feature; ~100 LOC across backend + UI

## Goal

Add a weekly variant of the existing Monthly Global Races Report. The user picks an ISO week (Mon–Sun); the system generates a 4-sheet Excel that matches the monthly format exactly but covers only the races whose date falls within that week.

## Non-goals

- No scheduler integration. Weekly is manual-only via UI/API.
- No new sheets, new columns, or new "weekly summary" content. Same writers as monthly.
- No cross-week ranges (e.g., 10-day windows). ISO week or nothing.
- No support for pre-1970 dates, alternative calendars, or non-ISO week numbering.

## User-facing behaviour

### Input
- Native HTML5 `<input type="week">` widget — Mon-anchored, in-browser pickers all use ISO weeks.
- Submitted to backend as `YYYY-Www` (e.g. `2026-W19`).

### Output
- Filename: `Weekly Global Races Report_<DD-DD MMM YYYY>_<DD.MM.YYYY>.xlsx`
  - Same-month: `Weekly Global Races Report_04-10 May 2026_11.05.2026.xlsx`
  - Cross-month: `Weekly Global Races Report_28 Apr-04 May 2026_11.05.2026.xlsx`
  - Cross-year: `Weekly Global Races Report_29 Dec 2025-04 Jan 2026_11.05.2026.xlsx`
- Sheets: identical 4-sheet structure to monthly (Race Overview / Elite Results / Sponsorship & Partnerships / Events' Highlights). Same writers, same scrape pipeline.
- Empty week → HTTP 400, no file written, no clutter in `data/reports/`.

## Architecture

### Layer 1: data filter (`app/data.py`)

Add one helper next to `races_for_month`:

```python
def races_for_iso_week(iso_year: int, iso_week: int) -> list[Race]:
    return [r for r in load_races()
            if r.date.isocalendar()[:2] == (iso_year, iso_week)]
```

`Race.date` is already a `datetime`. `isocalendar()` returns `(iso_year, iso_week, iso_weekday)` natively — no third-party dep needed.

### Layer 2: Excel writer (`app/excel_report.py`)

Refactor `generate_report` so the body becomes a private `_generate(races, filename) -> Path` helper. Both monthly and weekly entrypoints become thin wrappers.

```python
def _generate(races, filename: str) -> Path:
    facts_by_id = {r.id: scrape_race(r.id, r.official_url) for r in races}
    wb = Workbook(); wb.remove(wb.active)
    _write_race_overview(wb, races, facts_by_id)
    _write_elite_results(wb, races, facts_by_id)
    _write_sponsorship(wb, races, facts_by_id)
    _write_highlights(wb, races, facts_by_id)
    out = REPORTS_DIR / filename
    wb.save(out); return out

def generate_report(year: int, month: int) -> Path:
    races = data.races_for_month(year, month)
    if not races:
        raise ValueError(f"No shortlisted races for {year}-{month:02d}")
    today = datetime.now().strftime("%d.%m.%Y")
    fname = f"Monthly Global Races Report_{calendar.month_name[month]} {year}_{today}.xlsx"
    return _generate(races, fname)

def generate_weekly_report(iso_year: int, iso_week: int) -> Path:
    races = data.races_for_iso_week(iso_year, iso_week)
    if not races:
        raise ValueError(f"No shortlisted races for ISO week {iso_year}-W{iso_week:02d}")
    label = _format_week_label(iso_year, iso_week)
    today = datetime.now().strftime("%d.%m.%Y")
    fname = f"Weekly Global Races Report_{label}_{today}.xlsx"
    return _generate(races, fname)
```

Helper:

```python
def _format_week_label(iso_year: int, iso_week: int) -> str:
    """Convert an ISO week into a human-readable Mon-Sun span.

    Same month:    "04-10 May 2026"
    Cross-month:   "28 Apr-04 May 2026"
    Cross-year:    "29 Dec 2025-04 Jan 2026"
    """
    monday = datetime.fromisocalendar(iso_year, iso_week, 1)
    sunday = monday + timedelta(days=6)
    if monday.year != sunday.year:
        return f"{monday.strftime('%d %b %Y')}-{sunday.strftime('%d %b %Y')}"
    if monday.month != sunday.month:
        return f"{monday.strftime('%d %b')}-{sunday.strftime('%d %b %Y')}"
    return f"{monday.day:02d}-{sunday.day:02d} {monday.strftime('%b %Y')}"
```

`datetime.fromisocalendar` is in stdlib since Python 3.8 — no extra dep.

### Layer 3: API (`app/main.py`)

Add one POST endpoint next to the existing one. Existing monthly endpoint stays unchanged.

```python
@app.post("/api/reports/generate-weekly")
def api_generate_weekly(week: str = Query(..., description="ISO week YYYY-Www, e.g. 2026-W19")):
    import re
    m = re.fullmatch(r"(\d{4})-W(\d{2})", week)
    if not m:
        raise HTTPException(400, "week must be YYYY-Www, e.g. 2026-W19")
    iso_year, iso_week = int(m.group(1)), int(m.group(2))
    if not 1 <= iso_week <= 53:
        raise HTTPException(400, "ISO week must be 1-53")
    try:
        out = generate_weekly_report(iso_year, iso_week)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return JSONResponse({
        "file": out.name,
        "path": str(out.relative_to(ROOT)),
        "week": week,
    })
```

### Layer 4: UI (`static/index.html` + `static/app.js`)

In the existing "Generate now" card (currently lines 220–230 of `index.html`):

- **Add a Monthly/Weekly toggle pill row** above the input. Two small buttons; one is active.
- **Conditionally swap the input**: `x-show="genMode === 'monthly'"` for `<input type="month">`; `x-show="genMode === 'weekly'"` for `<input type="week">`.
- The single Build button works for both; `generate()` branches on `genMode`.

In `static/app.js`:

```js
genMode: 'monthly',         // new
genMonth: '2026-03',
genWeek: '2026-W19',        // new
generating: false,
genMessage: '',

async generate() {
  this.generating = true; this.genMessage = '';
  try {
    const url = this.genMode === 'weekly'
      ? `/api/reports/generate-weekly?week=${encodeURIComponent(this.genWeek)}`
      : `/api/reports/generate?month=${encodeURIComponent(this.genMonth)}`;
    const r = await fetch(url, { method: 'POST' });
    if (!r.ok) {
      this.genMessage = `Failed: ${(await r.json()).detail || r.status}`;
    } else {
      const j = await r.json();
      this.genMessage = `Generated ${j.file}`;
      await this.loadReports();
    }
  } catch (e) {
    this.genMessage = `Error: ${e.message}`;
  } finally {
    this.generating = false;
  }
},
```

The "Recent reports" list and download links work unchanged — both file types live in `data/reports/`.

## Error handling

| Case | Behaviour |
|---|---|
| Bad week format (`2026-19`, `2026W19`, etc.) | API returns 400 with parse-error message |
| ISO week 0 or 54 | API returns 400 |
| Empty week (no races) | API returns 400 with "No shortlisted races for ISO week 2026-W18" |
| Scrape failure mid-generation | Same as monthly today: bubbles up as 500. No retry logic added. |

## Testing & verification

No automated tests in the project. Manual verification:

1. Start server: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8765`
2. POST `/api/reports/generate-weekly?week=2026-W19` (Prague + Durban week, both ran 3 May)
3. Open the generated `.xlsx`. Expect:
   - 4 sheets in same order as monthly
   - 2 races on Race Overview (Prague, Durban)
   - Both podiums on Elite Results
   - Both sponsor blocks on Sponsorship sheet
   - Both highlight blocks on Highlights sheet
4. Re-score with `python -m tools.score_report` — Prague should still be 95%, Durban 86%.
5. POST `/api/reports/generate-weekly?week=2026-W18` (no races that week) — expect 400.
6. UI smoke test: toggle to Weekly, pick W19, click Build, confirm download.

## Risks & rollback

- **Risk:** `tools/score_report.py` defaults to comparing the *latest* xlsx in `data/reports/` against the March template. After this lands, the latest file may be a 2-race weekly, and the score table will only show 2 rows. Acceptable — pass an explicit path (`python -m tools.score_report data/reports/<file>.xlsx`) for monthly scores.
- **Rollback:** delete `generate_weekly_report` + `_format_week_label` + `races_for_iso_week` + the new endpoint + revert the UI toggle. Monthly path is unaffected.

## Out of scope (deferred)

- Auto-scheduling of weekly reports
- Email/Slack delivery of generated reports
- Custom date ranges (10-day, 14-day)
- "Weekly summary" sheet with narrative
- Bulk-generation (e.g., all weeks of a quarter)
