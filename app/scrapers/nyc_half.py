"""United Airlines NYC Half — https://www.nyrr.org/races/nyc-half

The NYC Half is operated by New York Road Runners (NYRR) and has run
since 2006 (with a 2014 hiatus and 2020/21 covid disruption). United
Airlines has been the title sponsor since 2017; previously NYC
Half-Marathon (Vodafone Wireless 2008–2010, NYC Half presented by
NYRR otherwise).

NYRR's site puts a Cloudflare virtual-corral queue in front of every
non-trivial path — even the race calendar redirects to a queue token.
The scraper attempts a plain GET and a browser GET; in either case if
we land outside the queue we extract whatever we can. Otherwise the
fallback layer (WA + AIMS) provides elite results.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


KNOWN_PARTNERS = [
    "New Balance",
    "Tata Consultancy Services",
    "Toyota",
    "ASICS",
    "Mastercard",
    "Poland Spring",
    "Gatorade Endurance",
    "Hospital for Special Surgery",
]


@register("united-airlines-nyc-half")
class NycHalfScraper(BaseScraper):
    official_url = "https://www.nyrr.org/races/nyc-half"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="New York Road Runners",
            title_sponsor="United Airlines",
            edition=20,            # 2006 first edition; 2026 is 20th (2014 ed not held; 2020/21 cancelled).
            inception_year=2006,
            other_sponsors="\n".join(KNOWN_PARTNERS),
            notes="NYRR site behind Cloudflare virtual corral; podium via WA fallback.",
        )

        soup = self.get(self.official_url) or self.get_via_browser(
            self.official_url, wait_after_load_ms=5000
        )
        if soup is None:
            return facts
        text = soup.get_text(" ", strip=True).lower()
        if "queue" in text[:400] or "verifying" in text[:400]:
            return facts

        # If we got real HTML, lift any /news/ or /run/blog/ link as a highlight.
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(" ", strip=True)
            if not txt or len(txt) < 18 or len(txt) > 200:
                continue
            if not any(k in href for k in ("/news/", "/run/blog/", "/run/photos-and-stories/")):
                continue
            full = href if href.startswith("http") else "https://www.nyrr.org" + href
            if "nyrr.org" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((txt[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
