"""Vodafone Prague Marathon — https://www.runczech.com/en/events/vodafone-prague-marathon-2026

31st edition, 2026-05-03. Title sponsor for 2026 is Vodafone (the race
was Volkswagen-titled in earlier years).

Pulls:
  - /en/events/vodafone-prague-marathon-2026 → sponsor list. Section
    headings ("Title partners", "Official partners", "Official media
    partners") split logos; logo filenames are stable enough to map back
    to clean brand names.
  - /en/results/vodafone-prague-marathon-2026?current_page=N → marathon
    results table. Top 3 men come from page 1 (overall ranking).
    Women appear lower in the overall standings, so the scraper pages
    forward until it has 3 entries flagged as women (age category
    starting with W or F).
  - /en/news → highlights (recap + 4 supporting articles)
  - The recap article ("…knows its winners!") confirms edition number.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Maps a substring of a logo filename → clean brand name. Probed against
# the events page; substring lookup tolerates the site's mixed naming
# (`logo_adidas.svg`, `dm_LogoKontur_1c.png`, `Garmin_Logo_Rgsd…`, etc.).
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
]

_FEMALE_CAT_RE = re.compile(r"^(W|F)\w+", re.I)


@register("prague-marathon")
class PragueMarathonScraper(BaseScraper):
    official_url = "https://www.runczech.com/en/events/vodafone-prague-marathon-2026"

    _EVENT_SLUG = "vodafone-prague-marathon-2026"
    _RESULTS_BASE = "https://www.runczech.com/en/results/vodafone-prague-marathon-2026"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="RunCzech",
            title_sponsor="Vodafone",
            inception_year=1995,
            edition=31,
        )

        self._extract_sponsors(facts)
        self._extract_mens_podium(facts)
        self._extract_womens_podium(facts)
        self._extract_highlights(facts)
        self._extract_results_meta(facts)
        if facts.finishers_total is None:
            self._extract_press_meta(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_results_meta(self, facts: RaceFacts) -> None:
        """Pull the authoritative marathon-finisher count from the
        results widget on /en/results/vodafone-prague-marathon-2026.

        The widget renders ``"9055 finishers total"`` (or similar) at
        the top of the page — that's the canonical number for the
        marathon distance. Prefer it over press-release prose like
        ``"nearly 12,000-strong pack"`` which conflates distances.
        """
        soup = self.get(self._RESULTS_BASE)
        if soup is None:
            return
        text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
        m = re.search(r"(\d{4,6})\s+finishers\s+total", text, re.I)
        if not m:
            return
        try:
            val = int(m.group(1))
        except ValueError:
            return
        if 3000 <= val <= 50000:
            facts.finishers_total = val

    # ------------------------------------------------------------------
    def _extract_press_meta(self, facts: RaceFacts) -> None:
        """Pull race statistics from RunCzech press releases.

        The pre-race "over 15,000 runners" article is stable; the
        post-race "personal stories" article carries the actual
        finisher count ("nearly 12,000-strong pack"). Capacity is
        also published in the elite-field preview.
        """
        press_paths = [
            ("/en/useful/for-the-media/news/"
             "a-battle-not-only-with-the-clock-but-with-willpower-and-the-elements-"
             "the-vodafone-prague-marathon-once-again-offered-hundreds-of-personal-stories"),
            ("/en/useful/for-the-media/news/"
             "over-15000-runners-from-more-than-100-countries-the-prague-international-marathon-"
             "is-just-around-the-corner-what-should-you-definitely-know-before-the-start"),
            ("/en/useful/for-the-media/news/"
             "fast-times-strong-competition-vodafone-prague-marathon-2026-presents-a-powerful-elite-field"),
        ]
        base = "https://www.runczech.com"
        for path in press_paths:
            soup = self.get(base + path)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            self._parse_press_text(text, facts)

    @staticmethod
    def _parse_press_text(text: str, facts: RaceFacts) -> None:
        # "nearly 12,000-strong pack" — actual race-day field count.
        # Prefer this over the pre-race "15,000 runners" count.
        m = re.search(r"(?:nearly|approximately|about|over|more than)?\s*([\d,\.]{4,8})[\s-]*strong\s+pack", text, re.I)
        if m:
            raw = m.group(1).replace(",", "").replace(".", "")
            try:
                val = int(raw)
                if 5000 <= val <= 50000:
                    facts.finishers_total = val
            except ValueError:
                pass
        if facts.finishers_total is None:
            m = re.search(r"(?:over|more than|nearly)\s+([\d,\.]{4,8})\s+runners\s+(?:from|completed|crossed)", text, re.I)
            if m:
                raw = m.group(1).replace(",", "").replace(".", "")
                try:
                    val = int(raw)
                    if 5000 <= val <= 50000:
                        facts.finishers_total = val
                except ValueError:
                    pass

        # Foreign:Czech ratio "54:46" → women percentage NOT derivable
        # from this; skip. We don't have a published women% for Prague.

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
        soup = self.get("https://www.runczech.com/en/news")
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
            if not any(k in tlow for k in ("vodafone", "prague")):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:120], full))

        # Lift the recap to the top.
        candidates.sort(key=lambda c: 0 if "knows its winner" in c[0].lower() else 1)
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
