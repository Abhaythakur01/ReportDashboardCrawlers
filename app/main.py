"""FastAPI app — serves dashboard, race API, and report generator."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import data
from app.excel_report import generate_report
from app.scrapers.registry import scraper_status
from app.scheduler import start_scheduler

ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT / "static"
REPORTS_DIR = ROOT / "data" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Race Report Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.on_event("startup")
def _on_startup() -> None:
    start_scheduler()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/races")
def api_races(
    month: int | None = Query(None, ge=1, le=12),
    year: int | None = Query(None, ge=2000, le=2100),
    country: str | None = None,
    label: str | None = None,
    category: str | None = None,
):
    races = data.load_races()
    if month:
        races = [r for r in races if r.month == month]
    if year:
        races = [r for r in races if r.year == year]
    if country:
        races = [r for r in races if r.country.lower() == country.lower()]
    if label:
        races = [r for r in races if r.label.lower() == label.lower()]
    if category:
        races = [r for r in races if r.category.lower() == category.lower()]
    return {
        "races": [r.to_dict() for r in races],
        "summary": data.summary(races),
    }


@app.get("/api/races/{race_id}")
def api_race(race_id: str):
    for r in data.load_races():
        if r.id == race_id:
            return r.to_dict()
    raise HTTPException(404, "Race not found")


@app.get("/api/scrapers")
def api_scrapers():
    return scraper_status()


@app.post("/api/reports/generate")
def api_generate_report(month: str = Query(..., description="YYYY-MM")):
    try:
        year_s, month_s = month.split("-")
        y, m = int(year_s), int(month_s)
    except Exception:
        raise HTTPException(400, "month must be YYYY-MM")
    out = generate_report(y, m)
    return JSONResponse({"file": out.name, "path": str(out.relative_to(ROOT)), "month": month})


@app.get("/api/reports")
def api_list_reports():
    files = sorted(REPORTS_DIR.glob("*.xlsx"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "name": f.name,
            "size": f.stat().st_size,
            "generated": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="seconds"),
        }
        for f in files
    ]


@app.get("/api/reports/{filename}")
def api_download_report(filename: str):
    path = REPORTS_DIR / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Report not found")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=filename,
    )
