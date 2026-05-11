"""World Athletics fallback data source.

For WA Label road races whose own site can't be scraped (Cloudflare,
JS-only SPAs without an exposed API), WA's results pages embed full
structured data in a Next.js ``__NEXT_DATA__`` script tag — top-3+
finishers per gender with name, nationality, time, age. WA isn't the
"official race site" in the strict sense, but it is the sanctioning
body for the race's labelling, so the data is authoritative.

A scraper using this module owns the race's WA competition ID. When WA
publishes a fresher edition, just bump the ID.

Usage:
    from app.scrapers._world_athletics import fetch_results
    res = fetch_results(7220354)
    res.competition_name, res.date_range, res.event("M").results[0].name
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List, Optional

import requests


_WA_BASE = "https://worldathletics.org/competition/calendar-results/results"
_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


@dataclass
class WAResult:
    place: int
    name: str
    nationality: str
    timing: str
    records: str = ""


@dataclass
class WAEvent:
    name: str
    gender: str  # "M" / "W"
    results: List[WAResult] = field(default_factory=list)


@dataclass
class WACompetition:
    competition_id: int
    name: str
    date_range: str
    venue: str
    ranking_category: str
    events: List[WAEvent] = field(default_factory=list)
    fetched_url: str = ""

    def event(self, gender: str) -> Optional[WAEvent]:
        for e in self.events:
            if e.gender.upper() == gender.upper():
                return e
        return None

    def men(self) -> Optional[WAEvent]:
        return self.event("M")

    def women(self) -> Optional[WAEvent]:
        return self.event("W")


def fetch_results(competition_id: int, *, timeout: int = 20) -> Optional[WACompetition]:
    url = f"{_WA_BASE}/{competition_id}"
    try:
        r = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (RaceReportDashboard) requests"},
        )
        r.raise_for_status()
    except Exception:
        return None

    m = _NEXT_DATA_RE.search(r.text)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    payload = (
        data.get("props", {}).get("pageProps", {}).get("calendarEventsResults") or {}
    )
    comp = payload.get("competition") or {}
    if not comp:
        return None

    out = WACompetition(
        competition_id=competition_id,
        name=comp.get("name") or "",
        date_range=comp.get("dateRange") or "",
        venue=comp.get("venue") or "",
        ranking_category=comp.get("rankingCategory") or "",
        fetched_url=url,
    )

    for et in payload.get("eventTitles") or []:
        for e in et.get("events") or []:
            ev = WAEvent(name=e.get("event") or "", gender=e.get("gender") or "")
            for race in e.get("races") or []:
                for res in race.get("results") or []:
                    competitor = res.get("competitor") or {}
                    place_str = (res.get("place") or "").rstrip(".")
                    try:
                        place = int(place_str)
                    except ValueError:
                        continue
                    ev.results.append(
                        WAResult(
                            place=place,
                            name=competitor.get("name") or "",
                            nationality=res.get("nationality") or "",
                            timing=res.get("mark") or "",
                            records=res.get("records") or "",
                        )
                    )
            ev.results.sort(key=lambda r: r.place)
            out.events.append(ev)

    return out
