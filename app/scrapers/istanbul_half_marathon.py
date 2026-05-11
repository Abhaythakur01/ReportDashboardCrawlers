"""Istanbul Half Marathon — https://maraton.istanbul/

The race is run by İBB Spor İstanbul (the sports arm of the Istanbul
Metropolitan Municipality), under the Turkish Athletics Federation
sanctioning. The site is shared between the half marathon (Apr) and
full marathon (Nov).

The site sits behind a full Cloudflare Turnstile that neither plain
``requests`` nor headless Playwright (with stealth, on Chromium or
Firefox) can clear in our testing — it requires either an interactive
solver or residential-IP routing.

Strategy:
  1. Try ``self.get()`` (plain) — currently 403.
  2. Try ``self.get_via_browser()`` (Playwright + stealth) — gets past
     mild CF gates on other sites; doesn't yet clear maraton.istanbul.
  3. Cross-cutting fallback layer (`app/scrapers/_fallbacks.py`) then
     fills the podium from World Athletics using the WA competition ID
     registered in ``data/race_metadata.yaml``.
"""
from __future__ import annotations

import re
from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Stable partners observed on the official site (DOM snapshot via Playwright
# session captured before CF was tightened).
KNOWN_OTHER_SPONSORS = [
    "Sportive",
    "Kahve Dünyası",
    "Zuber",
    "MG Türkiye",
    "Hamidiye",
    "Metro FM",
    "SKG",
]


@register("istanbul-half-marathon")
class IstanbulHalfMarathonScraper(BaseScraper):
    official_url = "https://maraton.istanbul/"

    _inception_year: int = 2006   # First Istanbul Half Marathon: April 2006
    _edition_2026: int = 21       # 2026 = 21st edition (every year since 2006)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="İBB Spor İstanbul (Istanbul Metropolitan Municipality Sports)",
            inception_year=self._inception_year,
            edition=self._edition_2026,
            title_sponsor="Türkiye İş Bankası",
            other_sponsors="\n".join(KNOWN_OTHER_SPONSORS),
        )

        soup = self._fetch_official(facts)
        if soup is not None:
            self._parse_official(soup, facts)
        # Podium / finisher fallbacks happen in the registry layer
        # (app/scrapers/_fallbacks.py) using race_metadata.yaml.
        return facts

    # ------------------------------------------------------------------
    def _fetch_official(self, facts: RaceFacts):
        """Try plain HTTP, then Playwright. Both currently expected to
        fail against Cloudflare; the call sites stay in place so the
        scraper picks up gracefully when the gate is loosened."""
        soup = self.get(self.official_url)
        if soup is not None:
            return soup

        soup = self.get_via_browser(self.official_url)
        if soup is not None:
            blob = soup.get_text(" ", strip=True)[:600].lower()
            if any(k in blob for k in ("just a moment", "verification", "enable javascript")):
                facts.notes = "Official site blocked by Cloudflare Turnstile."
                return None
            return soup
        facts.notes = "Official site unreachable (Cloudflare)."
        return None

    def _parse_official(self, soup, facts: RaceFacts) -> None:
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{1,3})\.\s*İstanbul\s+(Yarı\s+)?Marat", text)
        if m:
            ed = int(m.group(1))
            is_half = "Yarı" in m.group(0)
            if is_half and not isinstance(self, IstanbulMarathonScraper):
                facts.edition = ed
            elif not is_half and isinstance(self, IstanbulMarathonScraper):
                facts.edition = ed

        for a in soup.select("a[href*='/blog/']")[:5]:
            title = a.get_text(" ", strip=True)
            href = a.get("href", "")
            if title and href and len(title) > 10:
                if not href.startswith("http"):
                    href = self.official_url.rstrip("/") + href
                facts.highlights.append((title[:120], href))


@register("istanbul-marathon")
class IstanbulMarathonScraper(IstanbulHalfMarathonScraper):
    """The full marathon shares the same site, operator, and Cloudflare gate."""
    official_url = "https://maraton.istanbul/"
    _inception_year = 1979
    _edition_2026 = 47   # 2020 cancelled (COVID); all other years run since 1979.
