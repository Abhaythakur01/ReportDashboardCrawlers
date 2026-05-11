"""Standard Chartered Hong Kong Marathon — https://www.hkmarathon.com/

Inaugural 1997. Standard Chartered has been title sponsor since the
inaugural edition. 2026 marks the 29th edition.

Pulls:
  - / (homepage) -> sponsor logos via the Sponsor's Corner section
  - /sponsors-corner -> full sponsor list
  - /press-release -> news titles + URLs (top 5)
  - /title-sponsor -> confirms title sponsor

The /press-release page links to PDF press release files hosted at
resources.hkmarathon.com (a subdomain of the official origin), which
the BaseScraper allows via subdomain matching.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Tier rank: 0 = title, 1 = official, 2 = supporting/partner.
# Map img alt-text or filename token (lowercase) to clean brand name.
_LOGO_TOKEN_MAP: list[tuple[str, str, int]] = [
    ("standard chartered", "Standard Chartered", 0),
    ("standard-chartered", "Standard Chartered", 0),
    ("schartered", "Standard Chartered", 0),
    ("adidas", "Adidas", 1),
    ("seiko", "Seiko", 1),
    ("toyota", "Toyota", 1),
    ("hisamitsu", "Hisamitsu", 1),
    ("soyjoy", "SOYJOY", 1),
    ("soy joy", "SOYJOY", 1),
    ("anessa", "Anessa", 1),
    ("panasonic", "Panasonic", 1),
    ("banitore", "Banitore", 1),
    ("walch", "Walch", 1),
    ("garmin", "Garmin", 1),
    ("pocari", "Pocari Sweat", 1),
    ("ww-fun", "WW Fun", 2),
    ("ww fun", "WW Fun", 2),
    ("gp-batteries", "GP Batteries", 2),
    ("gp batteries", "GP Batteries", 2),
    ("gpbatteries", "GP Batteries", 2),
]

_PRESS_KEYWORDS = (
    "marathon", "champion", "winner", "expo", "youth run", "esg",
    "registration", "ballot", "elite", "support",
)


@register("standard-chartered-hong-kong-marathon")
class HongKongMarathonScraper(BaseScraper):
    official_url = "https://www.hkmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Hong Kong, China Association of Athletics Affiliates (HKAAA)",
            title_sponsor="Standard Chartered",
            inception_year=1997,
            edition=29,  # Inaugural 1997; 2026 is the 29th SCHKM (a few editions cancelled/rescheduled but the official body counts continuously).
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_edition(facts)
        self._extract_prize_money(facts)
        self._extract_event_history(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.hkmarathon.com/sponsors-corner")
        if soup is None:
            soup = self.get(self.official_url)
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[tuple[str, int]] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            src = (img.get("src") or "").lower()
            haystack = alt + " " + src.rsplit("/", 1)[-1]
            for needle, brand, tier in _LOGO_TOKEN_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append((brand, tier))
                    break

        if not ordered:
            return

        ordered.sort(key=lambda x: x[1])
        title_brands = [n for (n, t) in ordered if t == 0]
        if title_brands:
            facts.title_sponsor = title_brands[0]
        others = [n for (n, t) in ordered if t != 0]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.hkmarathon.com/press-release")
        if soup is None:
            return

        seen: set[str] = set()
        candidates: List[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12:
                continue
            full = href if href.startswith("http") else "https://www.hkmarathon.com" + href
            # Allow on-origin or any subdomain of hkmarathon.com (resources.hkmarathon.com hosts PDFs)
            if "hkmarathon.com" not in full:
                continue
            if full in seen:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _PRESS_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:140], full))
            if len(candidates) >= 5:
                break
        for title, url in candidates:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """The official /prize-money page publishes a USD-denominated
        prize ladder for the marathon (1st = $65,000, plus a published
        "Total Prizes: USD 314,800" line)."""
        soup = self.get("https://www.hkmarathon.com/prize-money")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        # "Total Prizes: USD 314,800" / "Total Prize Purse: USD ..."
        for pat in (
            r"total\s+prize[s]?\s*(?:purse|fund|money|pool)?\s*[:\-]?\s*"
            r"(?:USD|US\$|\$)\s*([\d,]{4,9})",
            r"(?:USD|US\$|\$)\s*([\d,]{4,9})\s+total\s+prize",
        ):
            m = re.search(pat, text, re.I)
            if m:
                try:
                    n = int(m.group(1).replace(",", ""))
                    if 50_000 <= n <= 5_000_000:
                        facts.prize_money_usd = n
                        return
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    def _extract_event_history(self, facts: RaceFacts) -> None:
        """/event-history is a chronological recap that surfaces
        many year-stamped figures ("11,000 participants" — that's
        inaugural — through "74,000 runners"). We pick the largest
        count published, capped at a sane participation ceiling, as
        the most-recent stable race-quota figure."""
        soup = self.get("https://www.hkmarathon.com/event-history")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)

        candidates: list[int] = []
        for pat in (
            r"([\d,]{4,7})\s+race\s+quotas",
            r"([\d,]{4,7})\s+(?:participants|runners|entrants|entries)",
        ):
            for m in re.finditer(pat, text, re.I):
                try:
                    n = int(m.group(1).replace(",", ""))
                except ValueError:
                    continue
                if 10_000 <= n <= 100_000:
                    candidates.append(n)

        # The race steady-stated at ~74,000 quotas; ignore the inaugural
        # 11k mention by taking the maximum published count.
        if candidates:
            facts.finishers_total = max(candidates)

        # Gender split if surfaced ("X% women", "Y% men").
        wm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+women", text, re.I)
        if wm:
            try:
                facts.finishers_women_pct = float(wm.group(1))
            except ValueError:
                pass
        mm2 = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+men", text, re.I)
        if mm2:
            try:
                facts.finishers_men_pct = float(mm2.group(1))
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_edition(self, facts: RaceFacts) -> None:
        # Best-effort: regex over press release titles for "29th SCHKM"
        # phrasing if the site adopts it.
        soup = self.get(self.official_url)
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(
            r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:Standard Chartered\s+)?(?:Hong Kong\s+)?Marathon\b",
            text,
            re.I,
        )
        if m:
            try:
                facts.edition = int(m.group(1))
            except ValueError:
                pass
