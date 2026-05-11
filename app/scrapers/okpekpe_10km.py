"""Okpekpe 10km Road Race — https://okpekperoadrace.com/

11th edition, scheduled for 2026-05-30 (postponed from May 23). World
Athletics Gold Label road race; first race in West Africa to earn a
WA Label.

The 2026 race hasn't taken place at the time of this scraper run, so
podium / finisher data isn't available. The scraper still produces a
useful row by extracting:

  - Sponsors / partners from the homepage logo strip (filenames are
    identifiable: ``afn-logo2.jpeg``, ``aims_logo_med2.jpeg``,
    ``wld_athlet.jpg``, ``pamod.jpg``, etc.)
  - Highlights (5 most recent blog articles)
  - Edition / organizer / inception (hardcoded — these are stable race
    facts that don't change race-to-race)

The /sponsors/ page itself only carries unlabelled "sponsor-1.png" etc.;
the homepage logo strip is the parseable source.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Filename substring → clean brand name. Probed against the homepage.
_LOGO_FILE_MAP: list[tuple[str, str]] = [
    ("aims_logo", "AIMS"),
    ("wld_athlet", "World Athletics"),
    ("afn-logo", "Athletics Federation of Nigeria"),
    ("pamod", "Pamodzi Sport Marketing"),
    ("m4stvlog", "M4ST Vlog"),
    ("dbn.jpg", "DBN"),
    ("zag.png", "ZAG"),
    ("wa_permits", "WA Gold Label"),
]

_HIGHLIGHT_KEYWORDS = (
    "okpekpe", "10km", "edition", "label", "ambassador", "elite",
    "history", "broadcast", "sponsor", "athletes", "edo",
)


@register("okpekpe-10km-road-race")
class OkpekpeScraper(BaseScraper):
    official_url = "https://okpekperoadrace.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Pamodzi Sport Marketing",
            title_sponsor="",
            edition=11,
            inception_year=2013,
            notes="Race scheduled 2026-05-30; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_prize_money(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Sum the published USD prize ladder.

        Site /race-info/prize-money/ lists the elite athlete USD ladder:
        $10,000 / $5,000 / $4,000 / $3,000 / $2,000 (per gender) plus
        course-record ($2,000) and African-record ($5,000) bonuses.
        Both gender ladders are identical, so total elite purse =
        2 × sum-of-ladder. We exclude record bonuses from the headline
        figure (variable, only paid on hit).
        """
        soup = self.get("https://okpekperoadrace.com/race-info/prize-money/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # Pull all USD amounts in order. The page interleaves men's and
        # women's columns per rank (e.g. "1st 10,000 US$ 10,000 US$"),
        # so consecutive duplicates collapse to a single ladder rung.
        amounts = re.findall(r"([\d,]{3,7})\s*US\$", text, re.I)
        values: list[int] = []
        for raw in amounts:
            try:
                v = int(raw.replace(",", ""))
                if 500 <= v <= 100_000:
                    values.append(v)
            except ValueError:
                continue

        # Collapse runs of identical adjacent values into one.
        ladder: list[int] = []
        for v in values:
            if ladder and ladder[-1] == v:
                continue
            ladder.append(v)

        # The descending elite ladder is the leading prefix. Stop at
        # the first non-strictly-descending step (that's a record bonus).
        clean: list[int] = []
        for v in ladder:
            if not clean or v < clean[-1]:
                clean.append(v)
            else:
                break

        if len(clean) >= 5 and clean[0] >= 5000:
            total_usd = sum(clean[:5]) * 2  # men + women
            if 10_000 <= total_usd <= 500_000:
                facts.prize_money_usd = total_usd

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower().rsplit("/", 1)[-1]
            for needle, brand in _LOGO_FILE_MAP:
                if needle in src and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://okpekperoadrace.com/blog/")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12:
                continue
            full = href if href.startswith("http") else "https://okpekperoadrace.com" + href
            if "okpekperoadrace.com" not in full or full in seen:
                continue
            tail = full.rstrip("/").rsplit("/", 1)[-1]
            if not tail or tail in {"blog", "news", "category", "author", "tag"}:
                continue
            if any(token in full for token in ("/category/", "/author/", "/tag/", "/page/", "/race-info/", "#")):
                continue
            slug = full.rstrip("/").split("/")[-1]
            if len(slug) < 20:  # short slugs are nav items, not articles
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:120], full))

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
