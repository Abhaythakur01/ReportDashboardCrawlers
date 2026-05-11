"""Yangzhou Half Marathon — https://www.yzmls.com/

Officially "Jianzhen International Half Marathon" / 鉴真国际半程马拉松,
held annually in Yangzhou, China since 2006 along the canal city's
historic core. The 10th international edition (and 20th overall, with
the race tracing roots to 2006 as the Jianzhen Memorial run) was held
2026-04-19.

The official site (``yzmls.com``) is largely a static landing page
and a Chinese-language results portal. The 2026 edition was a WA
Gold Label race.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("yangzhou-half-marathon")
class YangzhouHalfScraper(BaseScraper):
    official_url = "https://www.yzmls.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Yangzhou Municipal People's Government, Chinese Athletics "
                "Association, Jiangsu Provincial Sports Bureau"
            ),
            title_sponsor="",
            edition=21,            # 1st edition 2006; 2026 = 21st (continuous)
            inception_year=2006,
            notes="Site primarily a Chinese landing page; podium via WA fallback.",
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
            if "yzmls.com" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
