"""Doha Marathon by Ooredoo — https://dohamarathon.qa/

The .qa origin currently DNS-fails / refuses connections from outside
Qatar, so this scraper is intentionally minimal. It tries a single
homepage fetch via the strict origin check; if the request fails the
scraper still returns a ``RaceFacts`` payload populated with the
hardcoded organising / sponsorship facts that the public record
confirms (Ooredoo title sponsor, Qatar Olympic Committee involvement,
inaugural 2017 edition).

If the site later becomes reachable from this host, expand the scraper
in the same shape as ``dubai_marathon.py``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition|Doha Marathon)", re.I)

_HIGHLIGHT_KEYWORDS = ("doha", "marathon", "ooredoo", "qatar", "race", "elite", "winner")

_PARTNER_TOKENS: list[tuple[str, str]] = [
    ("ooredoo", "Ooredoo"),
    ("qatar olympic", "Qatar Olympic Committee"),
    ("aspire", "Aspire Zone Foundation"),
    ("qatar airways", "Qatar Airways"),
    ("qatar tourism", "Qatar Tourism"),
]


@register("doha-marathon-by-ooredoo")
class DohaMarathonScraper(BaseScraper):
    official_url = "https://dohamarathon.qa/"

    def scrape(self) -> RaceFacts:
        # Hardcoded facts — these stand alone if the site is unreachable.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Qatar Olympic Committee / Aspire Zone Foundation",
            title_sponsor="Ooredoo",
            inception_year=2017,
            notes="Site historically unreachable from non-Qatar IPs; falling back to hardcoded facts.",
        )

        home = self.get(self.official_url)
        if home is None:
            return facts

        # Site reachable → enrich what we can.
        text = home.get_text(" ", strip=True)
        m = _EDITION_RE.search(text)
        if m:
            try:
                facts.edition = int(m.group(1))
            except ValueError:
                pass

        seen: set[str] = set()
        ordered: list[str] = []
        for img in home.find_all("img"):
            haystack = ((img.get("alt") or "") + " " + (img.get("src") or "")).lower()
            for needle, brand in _PARTNER_TOKENS:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

        self._extract_highlights(home, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_highlights(self, soup, facts: RaceFacts) -> Optional[str]:
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://dohamarathon.qa" + ("" if href.startswith("/") else "/") + href
            if "dohamarathon.qa" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12 or len(title) > 160:
                continue
            tlow = title.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if href in seen:
                continue
            seen.add(href)
            facts.highlights.append((title[:140], href))
            if len(facts.highlights) >= 5:
                break
        return None
