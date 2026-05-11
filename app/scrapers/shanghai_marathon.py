"""Shanghai Marathon — https://www.shmarathon.com/

The Shanghai International Marathon ("上马") is a World Athletics Platinum
Label road race held annually in November. First edition 1996; the title
sponsor is Shanghai Pudong Development Bank ("SPD Bank"). The race is
organized by the Shanghai Municipal Sports Bureau and Shanghai Donghao
Lansheng Group.

The official site is geo-restricted from non-CN networks (the host is
unreachable from outside China — DNS works but TCP connect is refused or
times out). Even when reached, the page is a Vue SPA whose data comes
from an off-origin API host (``user-gw.mararun.com``); fetching that
host is forbidden by the BaseScraper origin check.

This scraper therefore hardcodes the stable institutional facts and
makes a best-effort attempt to fetch the homepage for sponsor logos /
news titles. When the homepage isn't reachable, the cross-cutting
fallback layer picks up podium data from World Athletics.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Shanghai Marathon documented partner roster (recent editions). Used as
# a stable fallback because the homepage is a Vue SPA and the sponsor
# logo strip is rendered from an off-origin API.
_DOCUMENTED_PARTNERS = [
    "Adidas",
    "China Eastern Airlines",
    "Pepsi",
    "Yili",
    "Garmin",
    "Decathlon",
    "Ganten",
]


@register("shanghai-marathon")
class ShanghaiMarathonScraper(BaseScraper):
    official_url = "https://www.shmarathon.com/"

    def scrape(self) -> RaceFacts:
        # 1996 inception; 2025 edition was the 28th (race not held in
        # 2020). 2026 edition is scheduled for late November 2026.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Shanghai Municipal Sports Bureau, "
                "Shanghai Donghao Lansheng (Group) Co., Ltd."
            ),
            title_sponsor="Shanghai Pudong Development Bank (SPD Bank)",
            other_sponsors="\n".join(_DOCUMENTED_PARTNERS),
            edition=29,
            inception_year=1996,
            notes=(
                "Site is a Vue SPA backed by an off-origin API "
                "(user-gw.mararun.com); institutional facts hardcoded."
            ),
        )

        # Best-effort: try to fetch the homepage HTML in case it
        # surfaces sponsor logos / news titles directly. The host is
        # geo-restricted from many non-CN networks; failure is silent.
        self._try_homepage_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _try_homepage_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        # The Shanghai Marathon site uses the same mararun.com SPA
        # framework as Beijing — the static HTML carries only the shell.
        # If a future redesign exposes news titles, we'll grab top 5.
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
