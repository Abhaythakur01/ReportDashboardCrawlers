"""AIMS (Association of International Marathons and Distance Races)
secondary data source.

Each race has a stable info page at
``aims-worldrunning.org/races/<aims_race_id>.html``. The page lists past
edition dates and links to "Read more" articles in AIMS' Distance
Running magazine — those articles often quote finisher / participant
counts and include rich race recaps.

This module fetches the race info page, finds the most recent recap
article matching a target year, scrapes the article text, and regexes
out finisher counts plus a podium block when available.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


_AIMS_BASE = "https://aims-worldrunning.org"

_FINISHERS_RE = re.compile(
    r"(?:over|nearly|approximately|some|about)?\s*"
    r"([\d,]{3,7})\s+(?:runners|finishers|competitors|participants)",
    re.I,
)
_EDITION_NUM_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+edition\b", re.I)


@dataclass
class AIMSRecap:
    aims_race_id: int
    article_url: str
    article_title: str
    article_date: str
    finishers: Optional[int] = None
    edition: Optional[int] = None
    text_excerpt: str = ""
    highlights: List[Tuple[str, str]] = field(default_factory=list)


def fetch_recap(
    aims_race_id: int,
    *,
    target_year: Optional[int] = None,
    timeout: int = 15,
) -> Optional[AIMSRecap]:
    """Fetch the most recent AIMS recap article for ``aims_race_id``.

    If ``target_year`` is given, prefer an article whose listing date
    contains that year; otherwise pick the most recent.
    """
    info_url = f"{_AIMS_BASE}/races/{aims_race_id}.html"
    try:
        r = requests.get(
            info_url,
            timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (RaceReportDashboard) requests"},
        )
        r.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(r.text, "lxml")

    # Walk the page in document order, tracking the most recent date
    # text that precedes each "Read more" link. The listing format is:
    #   "20 April 2026, 11am UTC | Double triumph in Istanbul | Read more…"
    candidates: list[tuple[str, str, str]] = []  # (date_text, title, url)
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = a.get_text(" ", strip=True)
        if "/articles/" not in href or "read more" not in label.lower():
            continue
        full = href if href.startswith("http") else _AIMS_BASE + href
        # Walk up parents looking for a context block that holds the
        # "<date> <title>" line. AIMS wraps each entry in a small block
        # with the date as the first text and the title as the second.
        ctx_text = ""
        node = a
        for _ in range(6):
            node = node.find_parent()
            if node is None:
                break
            t = node.get_text(" ", strip=True)
            if t and t != label:
                ctx_text = t
                break
        m = re.search(
            r"(\d{1,2})\s+(January|February|March|April|May|June|July|"
            r"August|September|October|November|December)\s+(\d{4})",
            ctx_text,
        )
        date_str = m.group(0) if m else ""
        title = ""
        if m:
            after = ctx_text[m.end():]
            # Strip the trailing time stamp ("11am UTC", "1pm UTC", etc.)
            after = re.sub(
                r"^[\s,|·\-]*\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*UTC\s*",
                "",
                after,
                flags=re.I,
            )
            after = re.sub(r"^[\s,|·\-]+", "", after)
            after = re.sub(r"Read more.*$", "", after, flags=re.I).strip()
            title = after[:140].strip()
        candidates.append((date_str, title or label, full))

    if not candidates:
        return None

    # Score and pick best
    def parse_dt(d: str) -> Optional[datetime]:
        try:
            return datetime.strptime(d, "%d %B %Y")
        except ValueError:
            return None

    scored: list[tuple[float, str, str, str]] = []
    for d, title, url in candidates:
        dt = parse_dt(d) if d else None
        score = dt.timestamp() if dt else 0
        if target_year and dt and dt.year == target_year:
            score += 1e12
        scored.append((score, d, title, url))
    scored.sort(reverse=True)
    _, date_str, title, article_url = scored[0]

    try:
        r2 = requests.get(article_url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        r2.raise_for_status()
    except Exception:
        return AIMSRecap(
            aims_race_id=aims_race_id,
            article_url=article_url,
            article_title=title,
            article_date=date_str,
        )
    art_soup = BeautifulSoup(r2.text, "lxml")
    article = art_soup.find("article") or art_soup.find("main") or art_soup
    text = article.get_text(" ", strip=True)

    out = AIMSRecap(
        aims_race_id=aims_race_id,
        article_url=article_url,
        article_title=title,
        article_date=date_str,
        text_excerpt=text[:1500],
    )

    if (m := _FINISHERS_RE.search(text)):
        try:
            out.finishers = int(m.group(1).replace(",", ""))
        except ValueError:
            pass
    if (m := _EDITION_NUM_RE.search(text)):
        try:
            out.edition = int(m.group(1))
        except ValueError:
            pass

    return out
