"""Burj2Burj Half Marathon — https://www.burj2burj.com/

2nd edition, 2026-02-08 in Dubai. Organised by Worlds Iconic LLC; the
inaugural edition ran in 2024 (the brand launched the route between the
Burj Khalifa and Burj Al Arab). The site is a Squarespace-style SPA so
plain ``requests`` will see most pages render server-side just fine for
nav, partner logos and basic copy. Podium data is not surfaced on the
official site, so this scraper concentrates on overview, organiser,
sponsorship and highlight links.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition|annual|Burj2Burj)", re.I)

_PARTNER_TOKENS: list[tuple[str, str]] = [
    ("asics", "ASICS"),
    ("forex", "FOREX.com"),
    ("dry store", "Dry Store"),
    ("drystore", "Dry Store"),
    ("coca-cola arena", "Coca-Cola Arena"),
    ("coca cola arena", "Coca-Cola Arena"),
    ("dubai sports council", "Dubai Sports Council"),
    ("department of tourism", "Dubai Department of Tourism"),
    ("dubai municipality", "Dubai Municipality"),
    ("rta", "Roads & Transport Authority (RTA)"),
    ("dubai police", "Dubai Police"),
]

_HIGHLIGHT_KEYWORDS = ("burj", "marathon", "half", "dubai", "race", "training", "expo", "route")


@register("burj2burj-half-marathon")
class Burj2BurjHalfMarathonScraper(BaseScraper):
    official_url = "https://www.burj2burj.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Worlds Iconic LLC",
            title_sponsor="",
            inception_year=2024,
            edition=2,  # 2024 was edition 1; 2026 is edition 2 (no 2025 edition)
        )

        home = self.get(self.official_url)
        if home is not None:
            text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(text)
            if m:
                try:
                    facts.edition = int(m.group(1))
                except ValueError:
                    pass
            self._extract_partners(home, facts)
            self._extract_highlights(home, facts)

        # Pull from /partners as well (logos there are clearer)
        partners = self.get("https://www.burj2burj.com/partners")
        if partners is not None:
            self._extract_partners(partners, facts)

        # Prize money lives on a dedicated /post/ article (the link
        # from /half-marathon → "Find all prize money details here").
        self._extract_prize_money(facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Sum the published AED prize ladders, convert to USD.

        The /post/prize-money-burj2burj-half-marathon-dubai-2026/
        article publishes:
          - Elite top-10 ladder (per gender)
          - Sub-purse breakthrough bonuses (excluded — variable)
          - Emirati top-3 ladder (per gender)
          - Age-group top-3 ladder (per gender)

        AED → USD at ~3.673 AED/USD (the dirham is dollar-pegged).
        """
        soup = self.get(
            "https://www.burj2burj.com/post/"
            "prize-money-burj2burj-half-marathon-dubai-2026"
        )
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # Pull ALL AED amounts in document order. Each per-gender ladder
        # is published once but paid to BOTH genders, so total = 2 ×
        # sum across published ladders.
        amounts = re.findall(r"AED\s*([\d,]+(?:\.\d+)?)", text, re.I)
        values: list[int] = []
        for raw in amounts:
            try:
                v = int(float(raw.replace(",", "")))
                if 100 <= v <= 1_000_000:
                    values.append(v)
            except ValueError:
                continue

        if not values:
            return

        # Identify the elite ladder: leading descending run starting
        # at the largest value (≥10,000 AED expected for top-10).
        elite: list[int] = []
        for v in values:
            if not elite:
                if v >= 10_000:
                    elite.append(v)
            elif v < elite[-1]:
                elite.append(v)
            else:
                break

        if not elite or len(elite) < 5:
            return

        # The remaining amounts after the elite ladder include the
        # 12,000 sub-purse bonuses (excluded) plus Emirati / age-group
        # ladders. We add the secondary ladders by skipping any value
        # that equals the sub-purse threshold (AED 12,000 — already
        # paid in the elite ladder so it's a duplicate-shaped value
        # in the bonus section). The Emirati / age-group ladders both
        # start at AED 5,000 — we sum any descending 5,000-anchored
        # ladders that follow.
        i = len(elite)
        # Skip the sub-purse 12,000 lines (one or two).
        while i < len(values) and values[i] == 12_000:
            i += 1

        secondary_total = 0
        while i < len(values):
            if values[i] >= 5_000:
                # Found start of a secondary ladder — collect descending.
                ladder = [values[i]]
                i += 1
                while i < len(values) and values[i] < ladder[-1]:
                    ladder.append(values[i])
                    i += 1
                secondary_total += sum(ladder)
            else:
                i += 1

        total_aed = (sum(elite) + secondary_total) * 2  # men + women
        # AED is pegged at 3.6725 / USD; round to nearest 100.
        usd = round(total_aed / 3.6725 / 100) * 100
        if 10_000 <= usd <= 5_000_000:
            facts.prize_money_usd = usd

    # ------------------------------------------------------------------
    def _extract_partners(self, soup, facts: RaceFacts) -> None:
        existing = set(filter(None, (s.strip() for s in facts.other_sponsors.split("\n"))))
        ordered: list[str] = list(existing)
        for img in soup.find_all("img"):
            haystack = ((img.get("alt") or "") + " " + (img.get("src") or "")).lower()
            for needle, brand in _PARTNER_TOKENS:
                if needle in haystack and brand not in existing:
                    existing.add(brand)
                    ordered.append(brand)
                    break
        # ASICS (or any future) title sponsor would be lifted here, but the
        # 2026 edition doesn't list one — leave title_sponsor empty.
        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_highlights(self, soup, facts: RaceFacts) -> Optional[str]:
        seen = {h[1] for h in facts.highlights}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://www.burj2burj.com" + ("" if href.startswith("/") else "/") + href
            if "burj2burj.com" not in href:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12 or len(title) > 160:
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
