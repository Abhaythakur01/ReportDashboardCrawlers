"""Shenzhen Marathon — https://www.szmarathon.com/

The Shenzhen International Marathon ("深马") is a World Athletics Gold
Label road race held annually in December. First edition 2013;
organized by the Shenzhen Municipal Government / Shenzhen Bureau of
Culture, Sports, Radio, Television and Tourism. Title sponsor in recent
editions has been Ping An Bank.

The official site is geo-restricted from non-CN networks (host actively
refuses connections from many regions outside mainland China). The
page itself is a Vue SPA.

Hardcodes the stable institutional facts; the cross-cutting fallback
layer fetches podium data from World Athletics for the latest edition.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_DOCUMENTED_PARTNERS = [
    "Ping An Bank",
    "Adidas",
    "China Resources Yibao",
    "Yili",
    "Vanke",
    "Tencent Sports",
]


@register("shenzhen-marathon")
class ShenzhenMarathonScraper(BaseScraper):
    official_url = "https://www.szmarathon.com/"

    def scrape(self) -> RaceFacts:
        # 1st edition 2013; race held annually since (with COVID
        # disruptions). 2026 edition is the 13th, scheduled for
        # December 2026.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Shenzhen Municipal Government, "
                "Shenzhen Bureau of Culture, Sports, Radio, "
                "Television and Tourism"
            ),
            title_sponsor="Ping An Bank",
            other_sponsors="\n".join(_DOCUMENTED_PARTNERS[1:]),
            edition=13,
            inception_year=2013,
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
