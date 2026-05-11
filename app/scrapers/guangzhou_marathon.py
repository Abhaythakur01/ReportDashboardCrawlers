"""Guangzhou Marathon — https://www.gz-marathon.com/

The Guangzhou Marathon ("广马") is a World Athletics Gold Label road race
held annually in December. First edition 2012, organized by the
Guangzhou Municipal Sports Bureau. Title sponsor in recent editions has
been HSBC (sponsorship has rotated; the report records the current
title sponsor).

The official site is geo-restricted from non-CN networks (DNS resolution
fails from many regions outside mainland China). The site itself is
also a Vue/SPA whose data is loaded from off-origin APIs.

This scraper hardcodes the stable institutional facts and makes a
best-effort attempt at the homepage. When the host is unreachable, the
cross-cutting fallback layer fetches podium data from World Athletics.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Documented Guangzhou Marathon partner roster (recent editions).
_DOCUMENTED_PARTNERS = [
    "Anta",
    "Guangzhou Automobile Group",
    "Pepsi",
    "Yili",
    "Ganten",
    "China Mobile",
]


@register("guangzhou-marathon")
class GuangzhouMarathonScraper(BaseScraper):
    official_url = "https://www.gz-marathon.com/"

    def scrape(self) -> RaceFacts:
        # 1st edition 2012; 2024 edition was the 13th (race paused
        # 2020-2021 for COVID). 2026 edition is the 15th.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Guangzhou Municipal Sports Bureau, "
                "Guangzhou Sports Federation"
            ),
            title_sponsor="HSBC",
            other_sponsors="\n".join(_DOCUMENTED_PARTNERS),
            edition=15,
            inception_year=2012,
            notes=(
                "Site is geo-restricted from non-CN networks; "
                "institutional facts hardcoded."
            ),
        )

        self._try_homepage_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _try_homepage_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12 or len(text) > 160:
                continue
            if "news" not in href.lower() and "article" not in href.lower():
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + href
            if full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text, full))
            if len(facts.highlights) >= 5:
                break
