"""Wuxi Marathon — https://www.wxim.org/

The Wuxi Marathon (formally the "Wuxi International Marathon" /
无锡马拉松) has run annually since 2017 along the cherry-blossom
corridor of Lake Tai. The 2026 edition (10th) was held 2026-03-22.

The official domain ``wxim.org`` is geofenced: outside mainland China
DNS resolution often fails. The scraper attempts to fetch and falls
back to hardcoded baseline facts; the WA + AIMS fallback layer fills
podiums.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("wuxi-marathon")
class WuxiMarathonScraper(BaseScraper):
    official_url = "https://www.wxim.org/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Wuxi Municipal People's Government, Chinese Athletics "
                "Association, Jiangsu Provincial Sports Bureau"
            ),
            title_sponsor="",
            edition=10,            # 1st edition 2017; 2026 = 10th
            inception_year=2017,
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
            if not text or len(text) < 10 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "wxim.org" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
