"""Generali Prague Half Marathon — https://www.runczech.com/en/events/generali-prague-half-marathon-2026

26th edition on 2026-03-28. Title sponsor: Generali Česká pojišťovna.
Same operator as the Vodafone Prague Marathon (RunCzech), so the
sponsor strip and results table follow the same shape — see
``prague_marathon.py`` for the pattern this scraper mirrors.

Pulls:
  - /en/events/generali-prague-half-marathon-2026 → sponsor logos
  - /en/results/generali-prague-half-marathon-2026?current_page=N
                                          → official results table.
                                            Top 3 men come from page 1
                                            (overall ranking); women
                                            need pagination because
                                            they fall further down the
                                            absolute-rank list.
  - /en/useful/for-the-media/news       → highlights (post-race recap
                                          when published; otherwise
                                          surrounding event coverage)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Substring of img filename → clean brand name. Mirrors the Prague
# Marathon scraper's mapping (the events share a partner roster).
_LOGO_NAME_MAP: list[tuple[str, str]] = [
    ("adidas", "adidas"),
    ("mattoni", "Mattoni"),
    ("dm_logo", "dm"),
    ("vf_logo", "Vodafone"),
    ("generali", "Generali Česká pojišťovna"),
    ("birell", "Birell"),
    ("unicredit", "UniCredit Bank"),
    ("svetuska", "Světuška Foundation"),
    ("letiste-praha", "Prague Airport"),
    ("hyu_logo", "Hyundai"),
    ("hyundai", "Hyundai"),
    ("garmin", "Garmin"),
    ("kosik", "Košík.cz"),
    ("ajeto", "Ajeto Glass"),
    ("komwag", "KOMWAG"),
    ("johnny-servis", "Johnny Servis"),
    ("forbes", "Forbes"),
    ("ct_title", "Czech Television (ČT)"),
    ("radiozurnal", "Radiožurnál"),
    ("denikcz", "Deník.cz"),
    ("reporter", "Reporter Magazine"),
    ("hilton", "Hilton Prague"),
]

_FEMALE_CAT_RE = re.compile(r"^(W|F)\w+", re.I)


@register("generali-prague-half-marathon")
class PragueHalfMarathonScraper(BaseScraper):
    # Pin to the canonical 2026 event page; the legacy index.shtml URL
    # 404s on the live site.
    official_url = "https://www.runczech.com/en/events/generali-prague-half-marathon-2026"

    _RESULTS_BASE = "https://www.runczech.com/en/results/generali-prague-half-marathon-2026"

    def __init__(self, official_url=None) -> None:  # noqa: ARG002
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="RunCzech",
            title_sponsor="Generali Česká pojišťovna",
            inception_year=1996,  # Prague Half Marathon began 1996
            edition=26,           # 2026 = 26th edition
        )

        self._extract_sponsors(facts)
        self._extract_mens_podium(facts)
        self._extract_womens_podium(facts)
        self._extract_highlights(facts)
        self._extract_finishers(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_finishers(self, facts: RaceFacts) -> None:
        """Pull the total finisher count from the results page summary.

        The RunCzech results page renders a "X finishers total" string
        above the standings table (e.g. "15636 finishers total" for the
        2026 edition).
        """
        soup = self.get(self._RESULTS_BASE)
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{4,6})\s+finishers\s+total", text, re.I)
        if m and facts.finishers_total is None:
            try:
                facts.finishers_total = int(m.group(1))
            except ValueError:
                pass

        # Demographics live on the live-race news feed — quote:
        # "There will be 17,000 runners from 117 nationalities, from
        #  which 58% are men and 42% women."
        news_soup = self.get(self.official_url + "/news-from-the-race")
        if news_soup is None:
            return
        ntext = news_soup.get_text(" ", strip=True)
        mm = re.search(
            r"(\d{1,2})\s*%\s+are\s+men\s+and\s+(\d{1,2})\s*%\s+women",
            ntext,
            re.I,
        )
        if mm:
            try:
                m_pct = float(mm.group(1))
                w_pct = float(mm.group(2))
                if 0 < m_pct < 100 and 0 < w_pct < 100 and abs(m_pct + w_pct - 100) <= 1:
                    if facts.finishers_men_pct is None:
                        facts.finishers_men_pct = m_pct
                    if facts.finishers_women_pct is None:
                        facts.finishers_women_pct = w_pct
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            fn = src.rsplit("/", 1)[-1]
            for needle, brand in _LOGO_NAME_MAP:
                if needle in fn:
                    if brand not in seen:
                        seen.add(brand)
                        ordered.append(brand)
                    break

        title = facts.title_sponsor
        others = [b for b in ordered if b != title]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_mens_podium(self, facts: RaceFacts) -> None:
        rows = self._fetch_results_rows(page=1)
        podium: List[PodiumEntry] = []
        for cols in rows:
            if len(cols) < 7:
                continue
            cat = cols[6]
            if _FEMALE_CAT_RE.match(cat):
                continue
            podium.append(self._row_to_podium(cols, len(podium) + 1))
            if len(podium) == 3:
                break
        facts.mens_podium = podium

    def _extract_womens_podium(self, facts: RaceFacts) -> None:
        podium: List[PodiumEntry] = []
        for page in range(1, 8):
            rows = self._fetch_results_rows(page=page)
            if not rows:
                break
            for cols in rows:
                if len(cols) < 7:
                    continue
                cat = cols[6]
                if not _FEMALE_CAT_RE.match(cat):
                    continue
                podium.append(self._row_to_podium(cols, len(podium) + 1))
                if len(podium) == 3:
                    break
            if len(podium) == 3:
                break
        facts.womens_podium = podium

    def _fetch_results_rows(self, page: int) -> list[list[str]]:
        url = f"{self._RESULTS_BASE}?current_page={page}"
        soup = self.get(url)
        if soup is None:
            return []
        out: list[list[str]] = []
        for tr in soup.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if not cells:
                continue
            if len(cells) >= 7 and re.fullmatch(r"\d+", cells[0]):
                out.append(cells)
        return out

    @staticmethod
    def _row_to_podium(cols: list[str], rank: int) -> PodiumEntry:
        name = cols[2]
        timing = cols[3]
        nationality = cols[5]
        return PodiumEntry(rank=rank, name=name, nationality=nationality, timing=timing)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.runczech.com/en/useful/for-the-media/news")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12:
                continue
            if "/news/" not in href:
                continue
            full = href if href.startswith("http") else "https://www.runczech.com" + href
            tlow = text.lower()
            if not any(k in tlow for k in ("generali", "half", "prague")):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:120], full))

        # Lift any post-race recap to position 1 if its title looks
        # like a winners announcement.
        candidates.sort(
            key=lambda c: 0 if ("knows its winner" in c[0].lower() and "half" in c[0].lower()) else 1
        )
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
