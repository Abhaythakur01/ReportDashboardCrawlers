"""Chevron Houston Marathon + Aramco Houston Half Marathon
— https://www.chevronhoustonmarathon.com/

Two races, one weekend, one website. The marathon (since 1972) carries
Chevron's title; the half (since 2002) carries Aramco's. Both are
organised by the Houston Marathon Committee. The 2026 weekend was
2026-01-18.

The /sponsors/ page surfaces sponsor logos as <img> tags; alt text is
mostly empty, but the WordPress upload filenames are descriptive
("CVX_Logo_Corp...", "Aramco-Logo-color...", "Brooks_Logo...") which
the scraper maps to clean brand names. The /category/press-releases/
listing is the source for highlights and recap text. Each post-race
recap quotes the prize purse for both races verbatim
("More than $190,000 in prize money is awarded to the top finishers
of the Chevron Houston Marathon and $70,000 is awarded for the top
finishers in the Aramco Houston Half Marathon.").
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# "More than $190,000 in prize money ... Chevron Houston Marathon" /
# "$70,000 is awarded for the top finishers in the Aramco Houston Half"
_MARATHON_PURSE_RE = re.compile(
    r"\$([\d,]{5,9})\s+in\s+prize\s+money[^.]*Chevron\s+Houston\s+Marathon",
    re.I,
)
_HALF_PURSE_RE = re.compile(
    r"\$([\d,]{4,9})\s+is\s+awarded[^.]*Aramco\s+Houston\s+Half\s+Marathon",
    re.I,
)


# Filename-substring (lowercase) → clean brand name.
_FILENAME_BRAND_MAP: list[tuple[str, str]] = [
    ("cvx_logo",         "Chevron"),
    ("chevron",          "Chevron"),
    ("aramco",           "Aramco"),
    ("brooks_logo",      "Brooks"),
    ("ff_logo_houston",  "Fellowship of the Finishers"),
    ("methodist",        "Houston Methodist"),
    ("garmin",           "Garmin"),
    ("miclb",            "Memorial Hermann IRONMAN"),
    ("cforce",           "C Force"),
    ("haku",             "Haku"),
    ("td-logo",          "TD"),
    ("abc13",            "ABC13 Houston"),
    ("cisco",            "Cisco"),
    ("houston-first",    "Houston First"),
    ("hchsa",            "Harris County Houston Sports Authority"),
    ("metro-logo",       "METRO"),
]

_HIGHLIGHT_KEYWORDS = (
    "marathon", "half", "houston", "chevron", "aramco", "champion",
    "winner", "record", "finisher", "results", "elite",
)


class _HoustonBase(BaseScraper):
    official_url = "https://www.chevronhoustonmarathon.com/"

    _title_filename_needle = ""
    _title_brand = ""
    _inception_year = 1972
    _edition_2026 = 0

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Houston Marathon Committee",
            title_sponsor=self._title_brand,
            edition=self._edition_2026,
            inception_year=self._inception_year,
        )
        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_prize_money(facts)
        self._extract_volunteers(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_volunteers(self, facts: RaceFacts) -> None:
        """Read the volunteer headcount off the /volunteers/ page.

        The page advertises ``More than 7,000 volunteers contribute…``
        for the entire race weekend (marathon + half + 5k). The figure
        is shared across both feeders (HMC runs all three races as one
        weekend), so we apply the same number to both registered IDs.
        """
        soup = self.get(self.official_url + "volunteers/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(
            r"(?:more\s+than|over)\s+(\d{1,2}[,]?\d{3})\s+volunteers",
            text,
            re.I,
        )
        if m and facts.volunteers is None:
            try:
                v = int(m.group(1).replace(",", ""))
                if 500 <= v <= 50000:
                    facts.volunteers = v
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Pull the prize purse from the latest post-race press release.

        HMC publishes a single post-race release each year (e.g. "Records
        Fall and U.S. Champions Shine ..." for 2026, "American Records
        Fall Again ..." for 2025) that quotes both purses verbatim near
        the bottom. We pick the most recent release that matches.
        """
        listing = self.get(self.official_url + "category/press-releases/")
        if listing is None:
            return
        # Listing posts are <h2><a href=...>Title</a></h2> stacked newest-first.
        candidates: List[Tuple[str, str]] = []
        seen: set[str] = set()
        for h in listing.select("h2 a, h3 a, h4 a"):
            href = h.get("href", "")
            title = h.get_text(" ", strip=True)
            if not href.startswith("http") or "chevronhoustonmarathon.com" not in href:
                continue
            if href in seen:
                continue
            seen.add(href)
            candidates.append((title, href))

        # Heuristic: post-race recaps usually have "records", "champions",
        # "fall", or a dollar amount in the title. Prefer those first.
        priority_keys = (
            "records fall", "champions shine", "american records",
            "post-race", "recap", "records-fall",
        )

        def is_recap(title_url: Tuple[str, str]) -> int:
            title = title_url[0].lower()
            return 0 if any(k in title for k in priority_keys) else 1

        candidates.sort(key=is_recap)

        marathon_purse = half_purse = None
        for _title, href in candidates[:6]:
            soup = self.get(href)
            if soup is None:
                continue
            body = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
            if marathon_purse is None:
                m = _MARATHON_PURSE_RE.search(body)
                if m:
                    try:
                        marathon_purse = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass
            if half_purse is None:
                m = _HALF_PURSE_RE.search(body)
                if m:
                    try:
                        half_purse = int(m.group(1).replace(",", ""))
                    except ValueError:
                        pass
            if marathon_purse and half_purse:
                break

        # Each subclass picks the correct purse based on its title brand.
        target = (
            marathon_purse if self._title_brand == "Chevron"
            else half_purse if self._title_brand == "Aramco"
            else None
        )
        if target and 10_000 <= target <= 5_000_000 and facts.prize_money_usd is None:
            facts.prize_money_usd = target

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url + "sponsors/")
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            alt = (img.get("alt") or "").lower()
            haystack = src.rsplit("/", 1)[-1] + " " + alt
            for needle, brand in _FILENAME_BRAND_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        # Strip out the title sponsor for this race; keep the other.
        others = [b for b in ordered if b.lower() != self._title_brand.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url + "news/")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 18 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + href
            if "chevronhoustonmarathon.com" not in full:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in {"news", "category", ""}:
                continue
            if "/category/" in full or "/tag/" in full or "#" in slug:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))


@register("chevron-houston-marathon")
class HoustonMarathonScraper(_HoustonBase):
    _title_filename_needle = "cvx_logo"
    _title_brand = "Chevron"
    _inception_year = 1972
    _edition_2026 = 54   # 1st edition 1972; 2026 = 54th


@register("aramco-houston-half-marathon")
class HoustonHalfScraper(_HoustonBase):
    _title_filename_needle = "aramco"
    _title_brand = "Aramco"
    _inception_year = 2002
    _edition_2026 = 25   # 1st edition 2002; 2026 = 25th
