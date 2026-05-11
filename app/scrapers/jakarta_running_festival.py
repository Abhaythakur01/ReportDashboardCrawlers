"""Jakarta Running Festival Half Marathon
— https://jakartarunningfestival.com/

Indonesia's flagship half-marathon, held in Jakarta since 2018. The
2026 edition is held 2026-06-28. Inaugurated by the Jakarta provincial
government in partnership with Inspiro Asia (the operator) and B&K
Sports as the local promoter.

The official domain often fails DNS lookup outside of Indonesia (and
the site itself is JS-rendered). The scraper provides baseline
hardcoded facts; podium / finisher data comes from the fallback layer
(World Athletics).
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("jakarta-running-festival-half-marathon")
class JakartaRunningFestivalScraper(BaseScraper):
    official_url = "https://jakartarunningfestival.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Inspiro Asia, Jakarta Provincial Government",
            title_sponsor="",
            edition=8,             # 1st edition 2018; 2026 = 8th (skipping 2020 covid)
            inception_year=2018,
            notes="Official domain often unreachable; podium via WA fallback.",
        )
        soup = self.get(self.official_url) or self.get_via_browser(
            self.official_url, wait_after_load_ms=4000
        )
        if soup is None:
            return facts
        seen: set[str] = set()
        for a in soup.find_all("a", href=True)[:200]:
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "jakartarunningfestival.com" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
