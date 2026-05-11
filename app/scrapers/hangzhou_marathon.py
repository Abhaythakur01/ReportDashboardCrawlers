"""Hangzhou Marathon — https://www.hzmarathon.com/

The Hangzhou Marathon (杭州马拉松) has run annually since 1987, with
the modern WA-Elite-Label era beginning in 2014 (when the race
re-launched under city sponsorship). The 2026 edition is scheduled
for 2026-11-08; under the project's "current month" convention this
race appears in the November 2026 report.

The site is geofenced (DNS often fails outside CN) and JS-rendered.
The scraper provides hardcoded baseline facts and tries a fetch; WA
fallback handles elite data.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("hangzhou-marathon")
class HangzhouMarathonScraper(BaseScraper):
    official_url = "https://www.hzmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Hangzhou Municipal People's Government, Hangzhou Sports "
                "Bureau, Chinese Athletics Association"
            ),
            title_sponsor="",
            edition=39,           # Race traces to 1987; 2026 = 39th continuous edition.
            inception_year=1987,
            notes="Official domain often unreachable outside CN; podium via WA fallback.",
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
            if not text or len(text) < 8 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "hzmarathon.com" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
