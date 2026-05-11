"""Nagoya Women's Marathon — https://womens-marathon.nagoya/en/

Officially the world's largest women-only marathon (Guinness-recognised
in past editions). Race lineage:
  - 1980: Nagoya International Women's Marathon (elite-only) launched
  - 1984: 5th edition; first IAAF-listed running
  - 2012: rebranded to "Nagoya Women's Marathon" with mass-participation
The org keeps a continuous edition count starting from 1980, so the
2026 edition is the 47th.

Pulls:
  - /en/                   -> sponsor logos via alt-text/filename map
  - /en/outline/           -> organizers + edition (regex fallback)
  - /en/news/              -> news items (JS-rendered; degrades gracefully)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# alt-text or filename token (lowercase) -> (clean brand, tier).
# Tier: 0 = title/gold, 1 = silver, 2 = bronze, 3 = official partner.
_LOGO_TOKEN_MAP: list[tuple[str, str, int]] = [
    ("niterra", "Niterra", 0),
    ("new balance", "New Balance", 1),
    ("newbalance", "New Balance", 1),
    ("nb-logo", "New Balance", 1),
    ("aeon", "AEON", 2),
    ("toyota", "Toyota", 3),
    ("seiko", "Seiko", 3),
    ("fujipan", "Fujipan", 3),
    ("aquarius", "Aquarius", 3),
    ("vantelin", "Vantelin Kowa", 3),
    ("dai-ichi", "Dai-ichi Life", 3),
    ("daiichi", "Dai-ichi Life", 3),
    ("morinaga", "Morinaga", 3),
    ("tcb", "TCB Group", 3),
    ("sugi", "Sugi Holdings", 3),
    ("marukome", "Marukome", 3),
    ("mizuno", "Mizuno", 3),
]


@register("nagoya-women-s-marathon")
class NagoyaWomensMarathonScraper(BaseScraper):
    official_url = "https://womens-marathon.nagoya/en/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Japan Association of Athletics Federations (JAAF), "
                "Aichi Prefecture, Nagoya City, Nagoya Sports Promotion "
                "Association, The Chunichi Shimbun"
            ),
            title_sponsor="",  # No formal title sponsor; Niterra is the gold tier.
            inception_year=1980,
            edition=47,  # 1980 = 1st; 2026 = 47th edition.
        )

        self._extract_sponsors(facts)
        self._extract_outline(facts)
        self._extract_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
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
        # Niterra is the lead "Gold Sponsor" — surface as title sponsor when present.
        if any(t == 0 for _, t in ordered):
            facts.title_sponsor = "Niterra"
        others = [n for (n, t) in ordered if (n != facts.title_sponsor)]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_outline(self, facts: RaceFacts) -> None:
        soup = self.get("https://womens-marathon.nagoya/en/outline/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"\b(\d{1,3})(?:st|nd|rd|th)\b", text)
        # Only accept if context clearly references this race
        if m and ("nagoya" in text.lower() or "marathon" in text.lower()):
            try:
                ed = int(m.group(1))
                # Sanity bound: edition must be 30..100
                if 30 <= ed <= 100:
                    facts.edition = ed
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        # The /en/news/ page is JS-rendered; try a static fetch first and
        # fall back to the homepage where news teasers may appear.
        seen: set[str] = set()
        candidates: List[tuple[str, str]] = []
        for url in (
            "https://womens-marathon.nagoya/en/news/",
            "https://womens-marathon.nagoya/en/",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 12:
                    continue
                full = href if href.startswith("http") else "https://womens-marathon.nagoya" + href
                if "womens-marathon.nagoya" not in full:
                    continue
                # Only individual news articles
                if not re.search(r"/(en/)?news/[^/]+/?$", full):
                    continue
                if full in seen:
                    continue
                seen.add(full)
                candidates.append((text[:140], full))
                if len(candidates) >= 5:
                    break
            if candidates:
                break

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
