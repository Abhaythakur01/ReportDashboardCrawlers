"""Loader for the shortlisted races + official-site URL registry."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
SHORTLIST_XLSX = ROOT / "Shortlisted Races (2026).xlsx"
URLS_JSON = DATA_DIR / "race_urls.json"

MONTHS = {
    "JANUARY": 1, "FEBRUARY": 2, "MARCH": 3, "APRIL": 4,
    "MAY": 5, "JUNE": 6, "JULY": 7, "AUGUST": 8,
    "SEPTEMBER": 9, "OCTOBER": 10, "NOVEMBER": 11, "DECEMBER": 12,
}


@dataclass
class Race:
    id: str
    date: datetime
    name: str
    venue: str
    country: str
    category: str
    label: str
    official_url: Optional[str] = None

    @property
    def month(self) -> int:
        return self.date.month

    @property
    def year(self) -> int:
        return self.date.year

    @property
    def date_iso(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    def to_dict(self) -> dict:
        d = asdict(self)
        d["date"] = self.date_iso
        d["month"] = self.month
        d["year"] = self.year
        return d


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:80]


def _load_urls() -> dict[str, str]:
    if URLS_JSON.exists():
        return json.loads(URLS_JSON.read_text(encoding="utf-8"))
    return {}


def load_races() -> list[Race]:
    wb = openpyxl.load_workbook(SHORTLIST_XLSX, data_only=True)
    ws = wb["Sheet1"]
    urls = _load_urls()
    races: list[Race] = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(v is None for v in row):
            continue
        first = row[0]
        if isinstance(first, str) and first.strip().upper().split()[0] in MONTHS:
            continue
        if not isinstance(first, datetime):
            continue
        date, name, venue, country, category, label = row[:6]
        name = (name or "").strip()
        if not name:
            continue
        rid = _slug(name)
        races.append(
            Race(
                id=rid,
                date=date,
                name=name,
                venue=(venue or "").strip(),
                country=(country or "").strip(),
                category=(category or "").strip(),
                label=(label or "").strip(),
                official_url=urls.get(rid),
            )
        )
    races.sort(key=lambda r: (r.date, r.name))
    return races


def races_for_month(year: int, month: int) -> list[Race]:
    return [r for r in load_races() if r.year == year and r.month == month]


def summary(races: list[Race]) -> dict:
    by_label: dict[str, int] = {}
    by_category: dict[str, int] = {}
    by_country: dict[str, int] = {}
    by_month: dict[int, int] = {}
    for r in races:
        by_label[r.label] = by_label.get(r.label, 0) + 1
        by_category[r.category] = by_category.get(r.category, 0) + 1
        by_country[r.country] = by_country.get(r.country, 0) + 1
        by_month[r.month] = by_month.get(r.month, 0) + 1
    return {
        "total": len(races),
        "by_label": by_label,
        "by_category": by_category,
        "by_country": by_country,
        "by_month": by_month,
        "countries": sorted(by_country.keys()),
        "labels": sorted(by_label.keys()),
        "categories": sorted(by_category.keys()),
    }


if __name__ == "__main__":
    rs = load_races()
    print(f"Loaded {len(rs)} races")
    s = summary(rs)
    print(json.dumps(s, indent=2))
