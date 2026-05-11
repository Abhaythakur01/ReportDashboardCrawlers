"""Mexico City Marathon Telcel — https://www.maratoncdmx.com/

The Maratón de la Ciudad de México (Maratón CDMX), title-sponsored by
Telcel, is one of the largest marathons in Latin America. The race
debuted in 1983; the 2025 edition (43rd) was held on 31 August 2025.

The official site at maratoncdmx.com is intermittently unreachable from
non-MX networks (DNS / ECONNREFUSED). This scraper attempts the
homepage fetch behind the strict origin check; on failure it returns a
``RaceFacts`` payload with hardcoded organising / sponsorship facts
(Telcel title sponsor, INDEPORTE / CDMX Government as organiser,
inaugural 1983 edition).

If the site becomes reachable, expand the scraper to extract edition,
news, podiums in the same shape as ``dubai_marathon.py``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(
    r"\b(?:(\d{1,3})(?:st|nd|rd|th|°|º|ª)\s+(?:edition|edici[oó]n|aniversario|maratón)|"
    r"(?:edici[oó]n|maratón)\s+n[uú]mero\s+(\d{1,3}))",
    re.I,
)

_HIGHLIGHT_KEYWORDS = (
    "marathon", "maratón", "telcel", "cdmx", "mexico", "méxico", "indeporte",
    "elite", "winner", "ganador", "resultado",
)

_PARTNER_TOKENS: list[tuple[str, str]] = [
    ("telcel", "Telcel"),
    ("indeporte", "INDEPORTE"),
    ("cdmx", "Government of Mexico City"),
    ("ciudad de méxico", "Government of Mexico City"),
    ("ciudad de mexico", "Government of Mexico City"),
    ("under armour", "Under Armour"),
    ("garmin", "Garmin"),
    ("powerade", "Powerade"),
    ("gatorade", "Gatorade"),
    ("aeromexico", "Aeroméxico"),
    ("aeroméxico", "Aeroméxico"),
    ("ciel", "Ciel"),
]


@register("mexico-city-marathon-telcel")
class MexicoCityMarathonTelcelScraper(BaseScraper):
    official_url = "https://www.maratoncdmx.com/"

    def scrape(self) -> RaceFacts:
        # Hardcoded baseline facts — these stand alone if the site is unreachable.
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="INDEPORTE (Mexico City Sports Institute) / Government of Mexico City",
            title_sponsor="Telcel",
            inception_year=1983,
            edition=43,  # 2025 edition was the 43rd
            notes="Site intermittently unreachable from non-MX hosts; falling back to hardcoded facts.",
        )

        home = self.get(self.official_url)
        if home is None:
            return facts

        text = home.get_text(" ", strip=True)
        m = _EDITION_RE.search(text)
        if m:
            num = m.group(1) or m.group(2)
            try:
                facts.edition = int(num)
            except (TypeError, ValueError):
                pass

        seen: set[str] = set()
        ordered: list[str] = []
        for img in home.find_all("img"):
            haystack = ((img.get("alt") or "") + " " + (img.get("src") or "")).lower()
            for needle, brand in _PARTNER_TOKENS:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

        self._extract_highlights(home, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_highlights(self, soup, facts: RaceFacts) -> Optional[str]:
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.maratoncdmx.com" + ("" if href.startswith("/") else "/") + href
            if "maratoncdmx.com" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12 or len(title) > 200:
                continue
            tlow = title.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if href in seen:
                continue
            seen.add(href)
            facts.highlights.append((title[:140], href))
            if len(facts.highlights) >= 5:
                break
        return None
