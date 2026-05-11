"""Tokyo Marathon — official site: https://www.marathon.tokyo/en/

Scrapes:
  - news listing → highlights + the post-race "Has Ended" recap
  - that recap     → preliminary runner total ("welcomed N runners")

The Tokyo Marathon Foundation does not publicly disclose the prize purse
or the men's/women's split, so those fields stay blank.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# "welcomed 38,773 runners" / "37,785 runners (preliminary figure)"
_RUNNERS_RE = re.compile(
    r"welcomed\s+([\d,]{4,7})\s*runners",
    re.I,
)
_EDITION_RE = re.compile(r"In\s+its\s+(\d{1,3})(?:st|nd|rd|th)\s+edition", re.I)


@register("tokyo-marathon")
class TokyoMarathonScraper(BaseScraper):
    official_url = "https://www.marathon.tokyo/en/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Tokyo Marathon Foundation",
            inception_year=2007,
        )

        # Highlights — collect news entries from the official news listing.
        # Site structure: news cards under /en/news/
        soup = self.get(self.official_url + "news/")
        recap_url: str | None = None
        article_urls: List[Tuple[str, str]] = []
        if soup is not None:
            for card in soup.select("a[href*='/news/detail/']"):
                title = card.get_text(strip=True)
                href = card.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.marathon.tokyo" + href
                if not title:
                    continue
                article_urls.append((title, href))
                if len(facts.highlights) < 5:
                    facts.highlights.append((title, href))
                tlow = title.lower()
                if recap_url is None and "has ended" in tlow:
                    recap_url = href

        # The "Has Ended" post is the canonical runner-total source: it is
        # published by the Tokyo Marathon Foundation the same evening with
        # the preliminary participant figure (e.g. "welcomed 38,773 runners
        # (preliminary figure)" for 2026).
        if recap_url:
            self._extract_finishers(recap_url, facts)

        return facts

    def _extract_finishers(self, recap_url: str, facts: RaceFacts) -> None:
        rsoup = self.get(recap_url)
        if rsoup is None:
            return
        body = " ".join(
            p.get_text(" ", strip=True) for p in rsoup.find_all(["p", "div"])
        )
        m = _RUNNERS_RE.search(body)
        if m:
            try:
                n = int(m.group(1).replace(",", ""))
            except ValueError:
                n = 0
            if 10_000 <= n <= 200_000 and facts.finishers_total is None:
                facts.finishers_total = n

        em = _EDITION_RE.search(body)
        if em and facts.edition is None:
            try:
                facts.edition = int(em.group(1))
            except ValueError:
                pass
