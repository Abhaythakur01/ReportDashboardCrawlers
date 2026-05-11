"""C&D Xiamen Marathon — https://www.xmim.org/

The Xiamen Marathon ("厦马") is a World Athletics Platinum Label road
race held annually in early January. First edition 2003; organized by
the Xiamen Municipal Government and Chinese Athletic Association.
Title sponsor since 2014 is Xiamen C&D Inc. (the marathon's official
name is "C&D Xiamen Marathon").

The official site is reachable but is a UMI/Ant Design SPA — the
static HTML is just a shell pointing at ``/umi.e2e051c6.css`` and
client-side routing under ``/`` (every path returns the same shell).
The runtime fetches data from off-origin APIs we can't query.

We hardcode institutional facts; the cross-cutting fallback layer
fetches the podium for the latest edition from World Athletics.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Documented C&D Xiamen Marathon partner roster (recent editions).
_DOCUMENTED_PARTNERS = [
    "Anta",
    "Bank of Xiamen",
    "Yili",
    "Pepsi",
    "Ganten",
    "Hisense",
    "Xiamen Air",
]


@register("c-d-xiamen-marathon")
class XiamenMarathonScraper(BaseScraper):
    official_url = "https://www.xmim.org/"

    def scrape(self) -> RaceFacts:
        # 1st edition 2003; held annually since (with 2020-21 COVID
        # disruption). 2026 edition was the 23rd, held 2026-01-04.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Xiamen Municipal Government, "
                "Chinese Athletic Association"
            ),
            title_sponsor="Xiamen C&D Inc.",
            other_sponsors="\n".join(_DOCUMENTED_PARTNERS),
            edition=23,
            inception_year=2003,
            notes=(
                "Site is a UMI/Ant Design SPA backed by off-origin APIs; "
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
