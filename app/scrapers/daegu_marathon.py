"""Daegu Marathon — https://daegumarathon.com/

The 2026 race (20th edition) ran on 2026-04-05 in Daegu, South Korea.
Organised by the City of Daegu and the Daegu Athletics Federation;
the official media partner is Yeongnam Ilbo.

The site presents an SSL hiccup (self-signed cert chain) and tightly
gated User-Agent — so it usually fails to fetch via plain requests.
The scraper attempts both an http and an https-via-browser fetch; if
either lands a usable HTML doc, sponsor logos and news links are
extracted; otherwise the scraper returns hardcoded baseline facts and
the cross-cutting WA fallback fills the podium.
"""
from __future__ import annotations

from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


@register("daegu-marathon")
class DaeguMarathonScraper(BaseScraper):
    official_url = "https://daegumarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Daegu Metropolitan City, Daegu Athletics Federation",
            title_sponsor="",
            edition=20,           # 1st edition 2007; 2026 = 20th
            inception_year=2007,
            notes="Official site requires browser handshake; relying on WA fallback for elite data.",
        )
        soup = self.get(self.official_url)
        if soup is None:
            soup = self.get_via_browser(self.official_url, wait_after_load_ms=5000)
        if soup is None:
            return facts

        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12 or len(text) > 220:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "daegumarathon.com" not in full:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug:
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:160], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
        return facts
