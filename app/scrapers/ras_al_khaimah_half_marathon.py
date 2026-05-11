"""Ras Al Khaimah Half Marathon — https://rakhalfmarathon.com/

19th edition, 2026-02-14 on Al Marjan Island. Patronage of HH Sheikh
Saud bin Saqr Al Qasimi; ASICS title partner (3-year deal from 2026).

Pulls:
  - / → edition, sponsor logos
  - /news/ → highlight cards
  - /kamworor-and-anley-see-off-powerful-fields-…/ → top-3 podiums + finisher count
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition|Ras\s+Al\s+Khaimah)", re.I)
# Half-marathon times: "58:14", "67:22", "1:02:33"
_HM_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?)\b")
_PODIUM_LINE_RE = re.compile(
    r"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){1,3})\s*[\(\[]?\s*"
    r"(Kenya|Ethiopia|Bahrain|Tanzania|Uganda|Eritrea|Morocco|Burundi|UAE|"
    r"Israel|Japan|Great Britain|United States)\s*[\)\]]?\s*[-–—]?\s*"
    r"(\d{1,2}:\d{2}(?::\d{2})?)",
    re.I,
)
_COUNTRY_TO_ISO = {
    "kenya": "KEN", "ethiopia": "ETH", "bahrain": "BRN", "tanzania": "TAN",
    "uganda": "UGA", "eritrea": "ERI", "morocco": "MAR", "burundi": "BDI",
    "uae": "UAE", "israel": "ISR", "japan": "JPN", "great britain": "GBR",
    "united states": "USA",
}

_SPONSOR_TOKENS: list[tuple[str, str]] = [
    ("asics", "ASICS"),
    ("ras al khaimah tourism", "Ras Al Khaimah Tourism"),
    ("itp", "ITP Media Group"),
    ("rak police", "RAK Police"),
    ("bisleri", "Bisleri"),
    ("heart of rak", "Heart of RAK"),
    ("sec", "SEC Sports & Events"),
    ("al rabia", "Al Rabia FM"),
    ("gold 101", "Gold 101.3 FM"),
    ("radio 4", "Radio 4 FM"),
    ("ch4", "Channel 4"),
]

_HIGHLIGHT_KEYWORDS = ("kamworor", "anley", "yeshaneh", "ras al khaimah", "rak", "elite", "marathon", "asics")


@register("ras-al-khaimah-half-marathon")
class RasAlKhaimahHalfMarathonScraper(BaseScraper):
    official_url = "https://rakhalfmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="SEC Sports & Events (under patronage of HH Sheikh Saud bin Saqr Al Qasimi)",
            title_sponsor="ASICS",
            inception_year=2007,
            edition=19,
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
            self._extract_sponsors(home, facts)

        recap_url = self._extract_highlights(facts)
        if recap_url:
            self._extract_recap(recap_url, facts)

        self._extract_prize_money(facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Sum the published USD ladder from /race-info/prize-money/.

        The page lays out the half-marathon ladder under a "USD" header
        with twin men/women columns ("1st 20,000 1st 20,000 …" once
        the columns flatten in DOM order), then a 10km AED ladder.
        We anchor on the "USD" header and pull rank-prefixed amounts
        until we cross into the AED block.
        """
        soup = self.get("https://rakhalfmarathon.com/race-info/prize-money/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # Slice the USD section: from the first "USD" marker up to the
        # first "AED" marker (or end if the page is USD-only).
        usd_start = text.find("USD")
        if usd_start < 0:
            return
        aed_start = text.find("AED", usd_start)
        usd_section = text[usd_start: aed_start if aed_start > 0 else len(text)]

        # Each rank has paired amounts. Pull them via a rank-prefixed
        # regex so we ignore the "USD"/"WOMEN" header tokens.
        rank_amounts = re.findall(
            r"\b(?:1st|2nd|3rd|[4-9]th|10th)\s+([\d,]{3,8})",
            usd_section,
        )
        values: list[int] = []
        for raw in rank_amounts:
            try:
                v = int(raw.replace(",", ""))
                if 500 <= v <= 100_000:
                    values.append(v)
            except ValueError:
                continue

        # Collapse adjacent duplicates (men column == women column).
        ladder: list[int] = []
        for v in values:
            if ladder and ladder[-1] == v:
                continue
            ladder.append(v)

        # The descending half-marathon ladder is the leading prefix.
        clean: list[int] = []
        for v in ladder:
            if not clean or v < clean[-1]:
                clean.append(v)
            else:
                break

        if len(clean) >= 5 and clean[0] >= 10_000:
            total_usd = sum(clean) * 2  # men + women
            if 50_000 <= total_usd <= 1_000_000:
                facts.prize_money_usd = total_usd

    # ------------------------------------------------------------------
    def _extract_sponsors(self, soup, facts: RaceFacts) -> None:
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            haystack = ((img.get("alt") or "") + " " + (img.get("src") or "")).lower()
            for needle, brand in _SPONSOR_TOKENS:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        soup = self.get("https://rakhalfmarathon.com/news/")
        if soup is None:
            return None
        seen: set[str] = set()
        recap_url: Optional[str] = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://rakhalfmarathon.com" + href
            if "rakhalfmarathon.com" not in href:
                continue
            tail = href.split("rakhalfmarathon.com", 1)[-1].strip("/")
            if not tail or tail in {"news", "news/"} or tail.startswith("news/?") or tail.startswith("news/page"):
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
            if "kamworor" in href.lower() and "see-off" in href.lower() and recap_url is None:
                recap_url = href
            facts.highlights.append((title[:140], href))
            if len(facts.highlights) >= 5:
                break
        return recap_url

    # ------------------------------------------------------------------
    def _extract_recap(self, url: str, facts: RaceFacts) -> None:
        soup = self.get(url)
        if soup is None:
            return
        article = soup.find("article") or soup.find("main") or soup
        text = article.get_text("\n", strip=True)

        m = re.search(r"(?:more than|over|nearly|approximately)\s+([\d,]{3,7})\s+runners", text, re.I)
        if m:
            try:
                facts.finishers_total = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

        mens, womens = self._parse_podiums(text)
        if mens:
            facts.mens_podium = mens
        if womens:
            facts.womens_podium = womens

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_podiums(text: str) -> tuple[List[PodiumEntry], List[PodiumEntry]]:
        low = text.lower()
        women_idx = -1
        for key in ("women's podium", "women’s podium", "women's race", "women’s race"):
            i = low.find(key)
            if i != -1 and (women_idx == -1 or i < women_idx):
                women_idx = i
        if women_idx == -1:
            women_idx = len(text)
        men_section = text[:women_idx]
        women_section = text[women_idx:]

        def collect(section: str) -> List[PodiumEntry]:
            out: List[PodiumEntry] = []
            seen_names: set[str] = set()
            for m in _PODIUM_LINE_RE.finditer(section):
                name = m.group(1).strip()
                country = m.group(2).strip().lower()
                timing = m.group(3)
                if name in seen_names:
                    continue
                seen_names.add(name)
                out.append(
                    PodiumEntry(
                        rank=len(out) + 1,
                        name=name,
                        nationality=_COUNTRY_TO_ISO.get(country, ""),
                        timing=timing,
                    )
                )
                if len(out) == 3:
                    break
            return out

        return collect(men_section), collect(women_section)
