"""Bangsaen21 — https://www.bangsaen21.com/

Held in Bangsaen Beach, Chonburi, Thailand annually since 2017.
Organised by Mud & Bib Co., Ltd. with the Sports Authority of
Thailand. The 2026 edition was held 2026-04-12 (10th edition).

The official site is a Webflow build that, on first paint, only
serves a single hero image — meaningful sponsor and news data is
loaded asynchronously and does not appear in the static HTML. The
scraper extracts whatever <a> tags are visible and otherwise returns
hardcoded baseline facts; WA fallback fills podiums.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("bangsaen21")
class Bangsaen21Scraper(BaseScraper):
    official_url = "https://www.bangsaen21.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Mud & Bib Co., Sports Authority of Thailand",
            title_sponsor="",
            edition=10,           # 1st edition 2017; 2026 = 10th
            inception_year=2017,
            notes="Official site is a Webflow splash; podium via WA fallback.",
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
            if "bangsaen21.com" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
