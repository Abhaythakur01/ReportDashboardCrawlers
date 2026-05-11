"""Dubai Marathon — https://dubaimarathon.org/

25th edition, 2026-02-01. Title sponsor ASICS, organised by Dubai Sports
Council. The site is a clean WordPress install — homepage carries hero
news cards and the "Six Debut Wins In A Row" recap article (linked from
the homepage and from /news/melak-and-dessie-win-25th-dubai-marathon/)
holds the full top-3 men's and women's podium with times.

Pulls:
  - / (homepage) → edition, sponsor logos, news links
  - /news/melak-and-dessie-win-25th-dubai-marathon/ → podiums + finisher count
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition|Dubai Marathon|Anniversary)", re.I)
_PODIUM_LINE_RE = re.compile(
    r"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){1,3})\s*[\(\[]?\s*"
    r"(Ethiopia|Kenya|Rwanda|Uganda|Tanzania|Eritrea|Bahrain|Morocco|Burundi|UAE|United Arab Emirates|Israel|Japan|"
    r"Great Britain|Spain|France|Italy|Germany|Netherlands|United States|South Africa)\s*[\)\]]?\s*[-–—]?\s*"
    r"(\d{1,2}:\d{2}:\d{2})",
    re.I,
)
_COUNTRY_TO_ISO = {
    "ethiopia": "ETH", "kenya": "KEN", "rwanda": "RWA", "uganda": "UGA",
    "tanzania": "TAN", "eritrea": "ERI", "bahrain": "BRN", "morocco": "MAR",
    "burundi": "BDI", "uae": "UAE", "united arab emirates": "UAE",
    "israel": "ISR", "japan": "JPN", "great britain": "GBR", "spain": "ESP",
    "france": "FRA", "italy": "ITA", "germany": "GER", "netherlands": "NED",
    "united states": "USA", "south africa": "RSA",
}

_SPONSOR_TOKENS: list[tuple[str, str]] = [
    ("asics", "ASICS"),
    ("dubai sports council", "Dubai Sports Council"),
    ("dubai police", "Dubai Police"),
    ("rta", "Roads & Transport Authority (RTA)"),
    ("dubai municipality", "Dubai Municipality"),
    ("channel 4", "Channel 4"),
    ("mg-uae", "MG UAE"),
    ("bisleri", "Bisleri"),
    ("agenda", "Agenda"),
    ("itp", "ITP Media Group"),
    ("taqeef", "Taqeef"),
    ("ciel", "Ciel"),
]

_HIGHLIGHT_KEYWORDS = ("dubai", "marathon", "melak", "dessie", "record", "elite", "winner")


@register("dubai-marathon")
class DubaiMarathonScraper(BaseScraper):
    official_url = "https://dubaimarathon.org/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Dubai Sports Council",
            title_sponsor="ASICS",
            inception_year=2000,
            edition=25,
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
            recap_url = self._extract_highlights(home, facts)
            if recap_url:
                self._extract_recap(recap_url, facts)
        self._extract_prize_money(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """The /news-media/prize-money/ page lists a tiered prize
        ladder split across HTML tables (Marathon Open in USD, then
        UAE-nationals + 10km tables in AED). Walk the first USD table
        and sum the men+women columns to derive the headline open-
        division marathon purse."""
        soup = self.get("https://dubaimarathon.org/news-media/prize-money/")
        if soup is None:
            return

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            cells = [
                [c.get_text(" ", strip=True) for c in r.find_all(["th", "td"])]
                for r in rows
            ]
            # Find the USD currency-row to confirm we're on the open
            # marathon table (the AED/UAE-nationals tables come later).
            currency_row_idx = None
            for i, row in enumerate(cells):
                joined = " ".join(c.upper() for c in row)
                if "USD" in joined and "AED" not in joined:
                    currency_row_idx = i
                    break
            if currency_row_idx is None:
                continue

            men_total = 0
            women_total = 0
            for row in cells[currency_row_idx + 1:]:
                if len(row) < 3:
                    continue
                label = row[0].lower().strip()
                if not label or "total" in label:
                    continue
                try:
                    men = int(row[1].replace(",", "").strip() or "0")
                    women = int(row[2].replace(",", "").strip() or "0")
                except ValueError:
                    continue
                if 0 < men <= 200_000 and 0 < women <= 200_000:
                    men_total += men
                    women_total += women

            total = men_total + women_total
            if 100_000 <= total <= 5_000_000:
                facts.prize_money_usd = total
                return

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
        # Drop title sponsor from "other_sponsors"
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, soup, facts: RaceFacts) -> Optional[str]:
        seen: set[str] = set()
        recap_url: Optional[str] = None
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://dubaimarathon.org" + href
            if "dubaimarathon.org" not in href:
                continue
            if "/news/" not in href and "marathon" not in href:
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
            if "melak-and-dessie-win" in href and recap_url is None:
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

        # Finisher count. The 2026 recap reads: "drew a total of 20,000
        # entries, a record 4,000 of them in the marathon". Prefer the
        # marathon-specific number over the all-distances entry total.
        m = re.search(r"record\s+([\d,]{3,7})\s+(?:of\s+them\s+in\s+the\s+marathon|in\s+the\s+marathon|marathon|entries|runners)", text, re.I)
        if m:
            try:
                facts.finishers_total = int(m.group(1).replace(",", ""))
            except ValueError:
                pass
        else:
            m = re.search(r"([\d,]{4,7})\s+total\s+participants", text, re.I)
            if m:
                try:
                    facts.finishers_total = int(m.group(1).replace(",", ""))
                except ValueError:
                    pass

        # Spectator / volunteer blurbs if surfaced in the recap
        sm = re.search(r"([\d,]{3,7})\s*\+?\s+spectators", text, re.I)
        if sm:
            try:
                n = int(sm.group(1).replace(",", ""))
                if 1_000 <= n <= 5_000_000:
                    facts.spectators = n
            except ValueError:
                pass
        vm = re.search(r"([\d,]{3,5})\s+volunteers", text, re.I)
        if vm:
            try:
                n = int(vm.group(1).replace(",", ""))
                if 50 <= n <= 50_000:
                    facts.volunteers = n
            except ValueError:
                pass

        # Gender split blurb (rare on Dubai recaps but cheap to try)
        wm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+women", text, re.I)
        if wm:
            try:
                facts.finishers_women_pct = float(wm.group(1))
            except ValueError:
                pass
        mn = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+men", text, re.I)
        if mn:
            try:
                facts.finishers_men_pct = float(mn.group(1))
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
        # Split into men's / women's halves on the recap by gender keyword
        low = text.lower()
        women_idx = -1
        for key in ("women's race", "women’s race", "women's podium", "in the women"):
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
