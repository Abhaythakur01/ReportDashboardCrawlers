"""Generali Berliner Halbmarathon — https://www.berliner-halbmarathon.de/en/

The site redirects to www.generali-berliner-halbmarathon.de. The 2026
edition (the 45th) ran on 2026-04-05. SCC EVENTS publishes a
post-event race report that carries the registered-field count and
women percentage.

Pulls:
  - / (homepage / partner strip)         → sponsor logos
  - /en/news-media/news/detail/...       → race recap stats:
        record number registered, % women, edition, nation count.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Stable post-event race-report slug. SCC's CMS keeps these around; if
# the slug ever rotates, the scraper falls back to the news index.
_RECAP_PATHS = [
    "/en/news-media/news/detail/rennbericht-zum-generali-berliner-halbmarathon",
    "/en/news-media/news/detail/generali-berlin-half-marathon-kiptoo-and-amebaw-triumph-in-berlin-petros-breaks-german-record",
]

_NEWS_INDEX = "/en/news-media/news"

_HIGHLIGHT_KEYWORDS = (
    "berlin", "half", "halbmarathon", "kiptoo", "amebaw", "petros",
    "generali", "race report", "rennbericht",
)


@register("generali-berliner-halbmarathon")
class BerlinerHalbScraper(BaseScraper):
    # Use the canonical (post-redirect) host so origin checks still
    # pass for any sub-page we fetch.
    official_url = "https://www.generali-berliner-halbmarathon.de/en/"

    def __init__(self, official_url: Optional[str] = None) -> None:
        # The race-urls.json may carry the legacy host (berliner-halbmarathon.de),
        # which 301-redirects to the generali-* host. We always pin the
        # canonical host so the origin check covers /news-media/* sub-pages.
        super().__init__(official_url="https://www.generali-berliner-halbmarathon.de/en/")

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="SCC EVENTS",
            title_sponsor="Generali",
            inception_year=1981,  # First Berlin Half: 1981; 2026 = 45th
            edition=45,
        )

        self._extract_partners(facts)
        self._extract_recap(facts)
        self._extract_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_partners(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        # Sponsor list usually under footer with class containing "sponsor"
        for el in soup.select("[class*='sponsor'] a, [class*='partner'] a")[:30]:
            name = el.get_text(strip=True)
            if not name or len(name) > 60:
                continue
            if name in seen or name.lower() == facts.title_sponsor.lower():
                continue
            seen.add(name)
            ordered.append(name)
        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_recap(self, facts: RaceFacts) -> None:
        base = "https://www.generali-berliner-halbmarathon.de"
        for path in _RECAP_PATHS:
            soup = self.get(base + path)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            self._extract_meta(text, facts)
            if facts.finishers_total or facts.finishers_women_pct:
                return  # found something useful

    @staticmethod
    def _extract_meta(text: str, facts: RaceFacts) -> None:
        # "registered a record number of 42,563 runners from 134 nations
        #  for the 45th edition"
        m = re.search(
            r"(?:registered|brought|attracted)?\s*(?:a\s+)?(?:record\s+)?(?:number\s+of\s+)?"
            r"([\d,\.]{4,8})\s+runners\s+(?:from|in)\s+\d{1,3}\s+nations",
            text, re.I,
        )
        if m and facts.finishers_total is None:
            raw = m.group(1).replace(",", "").replace(".", "")
            try:
                facts.finishers_total = int(raw)
            except ValueError:
                pass
        else:
            # Fallback: "biggest German half marathon with a record
            # number of 40,721 runners"
            m = re.search(
                r"(?:record\s+number\s+of|with\s+a\s+(?:record\s+)?(?:field\s+of|total\s+of)?)?"
                r"\s*([\d,\.]{4,8})\s+runners",
                text, re.I,
            )
            if m and facts.finishers_total is None:
                raw = m.group(1).replace(",", "").replace(".", "")
                try:
                    val = int(raw)
                    if 5000 <= val <= 100000:
                        facts.finishers_total = val
                except ValueError:
                    pass

        # "46 % of them were women" or "46% women"
        m = re.search(r"(\d{1,2})\s*%\s+(?:of\s+them\s+were\s+)?women", text, re.I)
        if m:
            facts.finishers_women_pct = float(m.group(1))
            facts.finishers_men_pct = 100.0 - facts.finishers_women_pct

        # "45th edition"
        m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+edition", text, re.I)
        if m:
            try:
                ed = int(m.group(1))
                if 20 <= ed <= 80:
                    facts.edition = ed
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        if facts.highlights:
            return
        base = "https://www.generali-berliner-halbmarathon.de"
        soup = self.get(base + _NEWS_INDEX)
        if soup is None:
            return
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news-media/news/detail/" not in href:
                continue
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 14 or len(text) > 220:
                continue
            full = href if href.startswith("http") else base + href
            if full in seen:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
