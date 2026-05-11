"""Bank of China Beijing Marathon — https://www.beijing-marathon.com/

The Beijing Marathon ("北马") is China's oldest international marathon,
first held in 1981. World Athletics Platinum Label race; title sponsor
is Bank of China (since 2011, hence the official name "Bank of China
Beijing Marathon"). Organized by the Chinese Athletic Association,
Beijing Municipal Sports Bureau, and Beijing Sports Federation.

The official site is reachable but is a Vue SPA — the static HTML is
just a shell. The runtime fetches data from ``user-gw.mararun.com``
(the same back-end that powers Shanghai Marathon), which sits on a
different origin and is therefore off-limits to this scraper.

We hardcode the institutional facts the report needs and let the
cross-cutting fallback layer fetch podium results from World Athletics
once the most recent edition is published.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Documented Beijing Marathon partner roster (2024-2025 editions). Used
# as a stable fallback because the homepage is a Vue SPA and the sponsor
# logo strip is rendered from an off-origin API.
_DOCUMENTED_PARTNERS = [
    "Adidas",
    "Yili",
    "Mengniu",
    "Toyota",
    "Pepsi",
    "Ganten",
    "Beijing Hyundai",
]


@register("bank-of-china-beijing-marathon")
class BeijingMarathonScraper(BaseScraper):
    official_url = "https://www.beijing-marathon.com/"

    def scrape(self) -> RaceFacts:
        # Beijing Marathon: 1st edition 1981. The 2024 race was the 43rd
        # edition (numbering aligns with continuous yearly count from
        # 1981, with breaks netting the 43rd in 2024). 2026 edition is
        # the 45th, scheduled for early November 2026.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Chinese Athletic Association, "
                "Beijing Municipal Sports Bureau, "
                "Beijing Sports Federation"
            ),
            title_sponsor="Bank of China",
            other_sponsors="\n".join(_DOCUMENTED_PARTNERS),
            edition=45,
            inception_year=1981,
            notes=(
                "Site is a Vue SPA backed by an off-origin API "
                "(user-gw.mararun.com); institutional facts hardcoded."
            ),
        )

        # Best-effort: scan the static homepage HTML for any news links
        # the SPA shell happens to expose server-side.
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
