"""Sanlam Cape Town Marathon — https://capetownmarathon.com/

32nd edition, scheduled for 2026-05-24. First African candidate for
Abbott World Marathon Majors status. Title sponsor is Sanlam (the
race is officially the "Sanlam Cape Town Marathon").

Pulls:
  - / (homepage) → sponsor img alts. Major sponsors are surfaced via
    a clean alt-text → brand map; the broader sponsor strip on the
    homepage isn't fully expanded in the static HTML, so the scraper
    layers a documented partner list on top so the report still lists
    the full roster.
  - /news/ → highlights (5 most recent articles).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Alt text or filename substring → clean brand. Lowercase keys.
_ALT_BRAND_MAP: list[tuple[str, str]] = [
    ("sanlam",        "Sanlam"),
    ("adidas",        "adidas"),
    ("powerade",      "Powerade"),
    ("named sport",   "Named Sport"),
    ("kfm",           "KFM"),
    ("mediclinic",    "Mediclinic"),
    ("woolworths",    "Woolworths"),
    ("mercedes",      "Mercedes-Benz"),
    ("red bull",      "Red Bull"),
    ("castle lite",   "Castle Lite"),
    ("southern sun",  "Southern Sun Hotels"),
    ("europcar",      "Europcar"),
    ("runna",         "Runna"),
    ("coopah",        "Coopah"),
    ("carroll boyes", "Carroll Boyes"),
    ("city of cape town", "City of Cape Town"),
]

# Documented Cape Town Marathon partner roster (2026). Acts as a
# fallback in case the homepage HTML doesn't surface every sponsor —
# the page carries them in a JS-loaded carousel so the static HTML may
# only expose the first few.
_DOCUMENTED_PARTNERS = [
    "adidas", "Powerade", "City of Cape Town", "Mercedes-Benz",
    "Southern Sun Hotels", "Woolworths", "Named Sport", "Castle Lite",
    "KFM", "Mediclinic", "Red Bull", "Runna", "Carroll Boyes",
    "Coopah", "Europcar",
]

_HIGHLIGHT_KEYWORDS = (
    "marathon", "kipchoge", "sanlam", "cape town", "majors", "race",
    "weir", "schar", "spectator", "60 days", "training",
)


@register("cape-town-city-marathon")
class CapeTownMarathonScraper(BaseScraper):
    official_url = "https://capetownmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Cape Town Marathon Trust",
            title_sponsor="Sanlam",
            edition=32,
            inception_year=1994,
            notes="Race scheduled 2026-05-24; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_field_and_purse(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_field_and_purse(self, facts: RaceFacts) -> None:
        """Pull field size + prize purse from dedicated 2026 articles.

        The /2026-elite-field/ article publishes the increased prize
        purse (R4,862,500 base; R6,602,500 with record incentives) and
        the projected field (>27,000 marathon runners). The /sells-out
        -at-24000-marathon-entries/ article confirms 24,000 sold for
        the immediate prior edition.
        """
        urls = [
            "https://capetownmarathon.com/2026-elite-field/",
            "https://capetownmarathon.com/sanlam-renews-title-sponsorship/",
        ]
        for url in urls:
            soup = self.get(url)
            if soup is None:
                continue
            article = soup.find("article") or soup.find("main") or soup
            text = article.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)

            # Field size: "more than 27,000 marathon runners lining up"
            if facts.finishers_total is None:
                m = re.search(
                    r"(?:more than|over|approximately|nearly|projected)\s+"
                    r"([\d,]{4,8})\s+marathon\s+runners",
                    text, re.I,
                )
                if m:
                    raw = m.group(1).replace(",", "")
                    try:
                        val = int(raw)
                        if 10_000 <= val <= 100_000:
                            facts.finishers_total = val
                    except ValueError:
                        pass

            # Prize purse: "from R3,554,500 to R4,862,500" — pick the
            # second (current) value. Convert ZAR → USD at ~R18.5/USD.
            if facts.prize_money_usd is None:
                m = re.search(
                    r"from\s+R[\d,\.]+\s+to\s+R\s*([\d,\.]{5,12})",
                    text, re.I,
                )
                if m:
                    raw = m.group(1).replace(",", "").replace(".", "")
                    try:
                        zar = int(raw)
                        if 1_000_000 <= zar <= 100_000_000:
                            facts.prize_money_usd = round(zar / 18.5)
                    except ValueError:
                        pass

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        seen: set[str] = set()
        ordered: list[str] = []
        if soup is not None:
            for img in soup.find_all("img"):
                alt = (img.get("alt") or "").lower()
                src = (img.get("src") or "").lower()
                haystack = alt + " " + src
                for needle, brand in _ALT_BRAND_MAP:
                    if needle in haystack and brand not in seen:
                        seen.add(brand)
                        ordered.append(brand)
                        break

        # Layer documented partners on top of what we scraped.
        for brand in _DOCUMENTED_PARTNERS:
            if brand not in seen:
                seen.add(brand)
                ordered.append(brand)

        # Title sponsor is split out; the rest go in other_sponsors.
        others = [b for b in ordered if b.lower() != "sanlam"]
        facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://capetownmarathon.com/news/")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []

        # The news page uses plain <a> tags whose text is "<date> <title>".
        # Strip the date prefix when present.
        date_prefix = re.compile(
            r"^(?:[A-Z][a-z]{2,4}\.?\s+\d{1,2},\s+\d{4}|\d{4}-\d{2}-\d{2})\s+"
        )
        for a in soup.find_all("a", href=True):
            href = a["href"]
            raw = a.get_text(" ", strip=True)
            if not raw or len(raw) < 25 or len(raw) > 220:
                continue
            full = href if href.startswith("http") else "https://capetownmarathon.com" + href
            if full in seen or "capetownmarathon.com" not in full:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in {"news", "marathon"}:
                continue
            if "/category/" in full or "/tag/" in full:
                continue
            had_date_prefix = bool(date_prefix.match(raw))
            text = date_prefix.sub("", raw).strip()
            if not text or len(text) < 18:
                continue
            # Skip nav pages (no date prefix means it's not a dated article).
            if not had_date_prefix:
                continue
            year_match = re.search(r"^[A-Z][a-z]{2,4}\.?\s+\d{1,2},\s+(\d{4})", raw)
            year = int(year_match.group(1)) if year_match else 0
            if year < 2026:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:140], full))

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
