"""Cardiff Half Marathon — https://www.cardiffhalfmarathon.co.uk/

22nd edition on 2026-10-04. Organised by Run 4 Wales. The 2026
edition has no commercial title sponsor — earlier editions ran as
"Cardiff University / Cardiff Half Marathon", now downgraded to
"Cardiff University" as an Official Partner. Cardiff Airport is the
new headline Official Partner for 2026.

The race is in the future at scrape time, so podiums come from the
2025 archive (last completed edition).

Pulls:
  - /our-community/sponsors/   → tier-grouped partner list
  - /event-info/results/       → course records and 2025 winners
                                  (the in-house results page only shows
                                  the headline pair, per gender; full
                                  field results are off-site at
                                  Sporthive)
  - /event-info/about-the-race/ → confirms upcoming-edition date
  - /news-and-media/latest-news/ → highlights (entries open, partners,
                                    100 Club news, charity drive)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.cardiffhalfmarathon.co.uk"

# Sponsor sections on /our-community/sponsors/. The "Title Partner"
# section is empty in 2026, so we don't claim a title sponsor.
_SPONSOR_SECTIONS = {
    "title partner":     "title",
    "official partners": "official",
    "offical partners":  "official",   # site mis-spells the heading
    "lead charity":      "charity",
    "event associates":  "associate",
    "associate charity partners": "charity",
}

_TIME_HMS_RE = re.compile(r"(\d{1,2}:\d{2}:\d{2})")
_TIME_MS_RE = re.compile(r"\(\s*(\d{1,2}):(\d{2})\s*\)")
_NAT_TOKEN_RE = re.compile(r"\b(Kenya|Ethiopia|Great Britain|Uganda|United States|USA|Wales|England|Tanzania|Burundi|Eritrea)\b", re.I)
_NAT_MAP = {
    "kenya": "KEN",
    "ethiopia": "ETH",
    "great britain": "GBR",
    "uganda": "UGA",
    "united states": "USA",
    "usa": "USA",
    "wales": "WAL",
    "england": "GBR",
    "tanzania": "TAN",
    "burundi": "BDI",
    "eritrea": "ERI",
}


@register("cardiff-half-marathon")
class CardiffHalfMarathonScraper(BaseScraper):
    official_url = _BASE + "/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Run 4 Wales",
            title_sponsor="",  # No title sponsor for 2026
            inception_year=2003,
            edition=22,  # 2026 = 22nd edition (1st = 2003; cancelled 2020)
        )
        self._extract_sponsors(facts)
        self._extract_results(facts)
        self._extract_about(facts)
        self._extract_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_about(self, facts: RaceFacts) -> None:
        """Read the field size off the About-The-Race page.

        The page narrates the institutional history: ``It now attracts a
        mass race field of over 27,500 registered runners alongside
        world-class athletes…``. The 27,500 number is the registered
        field, not strictly finishers — but absent a published recap
        with a finisher tally, this is the best on-site stat available
        and matches Run 4 Wales' own communications.
        """
        soup = self.get(_BASE + "/event-info/about-the-race/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(
            r"over\s+(\d{1,2}[,]?\d{3})\s+registered\s+runners",
            text,
            re.I,
        )
        if m and facts.finishers_total is None:
            try:
                v = int(m.group(1).replace(",", ""))
                if 5000 <= v <= 60000:
                    facts.finishers_total = v
                    bits = facts.notes.split(" · ") if facts.notes else []
                    bits.append("finishers_total = registered field per About-The-Race")
                    facts.notes = " · ".join(b for b in bits if b)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/our-community/sponsors/")
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[str] = []
        current_role = ""
        # The sponsor page uses H2 for sections and H3 for brand names
        # within each section.
        for el in soup.find_all(["h2", "h3"]):
            if el.name == "h2":
                low = el.get_text(" ", strip=True).lower().strip()
                current_role = ""
                for needle, role in _SPONSOR_SECTIONS.items():
                    if needle in low:
                        current_role = role
                        break
                continue
            if el.name == "h3" and current_role:
                brand = el.get_text(" ", strip=True)
                if not brand or len(brand) > 80:
                    continue
                if brand in seen:
                    continue
                seen.add(brand)
                # No title sponsor — every brand goes into other_sponsors.
                ordered.append(brand)

        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_results(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/event-info/results/")
        if soup is None:
            return
        text = soup.get_text("\n", strip=True)

        # Pull the 2025 block (between the "2025" H2 and the "2024" H2).
        m = re.search(r"\b2025\b\s*\n(.*?)(?:\n\s*\b2024\b|\Z)", text, re.S)
        block = m.group(1) if m else text

        mens = self._parse_winner(block, gender="men")
        womens = self._parse_winner(block, gender="women")
        if mens:
            facts.mens_podium = mens
        if womens:
            facts.womens_podium = womens

    @staticmethod
    def _parse_winner(block: str, gender: str) -> List[PodiumEntry]:
        # "Winner Men:" / "Winner Woman:" headers, followed by name +
        # nationality + "(time)" on the next few lines.
        if gender == "men":
            head_re = re.compile(r"Winner\s+Men\s*:\s*(.+?)(?=Winner\s+(?:Woman|Wheelchair)|\Z)", re.I | re.S)
        else:
            head_re = re.compile(r"Winner\s+Woman\s*:\s*(.+?)(?=Winner\s+(?:Men|Wheelchair)|\Z)", re.I | re.S)
        m = head_re.search(block)
        if not m:
            return []
        snippet = m.group(1)
        # Time: H:MM:SS preferred, then M:SS in parens.
        timing = ""
        tm = _TIME_HMS_RE.search(snippet)
        if tm:
            timing = tm.group(1)
        else:
            tm = _TIME_MS_RE.search(snippet)
            if tm:
                timing = f"0:{int(tm.group(1)):02d}:{tm.group(2)}"
        # Nationality
        nat_code = ""
        nm = _NAT_TOKEN_RE.search(snippet)
        if nm:
            nat_code = _NAT_MAP.get(nm.group(1).lower(), "")
        # Name = first non-empty line, stripped of trailing nationality
        # or time tokens.
        name = ""
        for ln in (ln.strip() for ln in snippet.splitlines()):
            if not ln:
                continue
            if _NAT_TOKEN_RE.search(ln) or _TIME_HMS_RE.search(ln) or "(" in ln:
                continue
            name = ln
            break
        if not name:
            return []
        return [PodiumEntry(rank=1, name=name, nationality=nat_code, timing=timing)]

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/news-and-media/latest-news/")
        if soup is None:
            soup = self.get(self.official_url)
        if soup is None:
            return
        # The latest-news template renders article cards as
        # <h3|h4>Title</h3|h4> followed by a "Read More" anchor. Pair
        # each "Read More" link with its preceding heading to recover
        # the article title.
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            atext = a.get_text(" ", strip=True).lower()
            if "read more" not in atext:
                continue
            href = a["href"]
            full = href if href.startswith("http") else _BASE + href
            if "cardiffhalfmarathon.co.uk" not in full:
                continue
            tail = full.split("cardiffhalfmarathon.co.uk", 1)[-1].strip("/")
            if not tail or "/" in tail:
                continue
            if full in seen:
                continue
            heading = a.find_previous(["h2", "h3", "h4"])
            if heading is None:
                continue
            title = heading.get_text(" ", strip=True)
            if not title or len(title) < 8 or title.lower() == "latest news":
                continue
            seen.add(full)
            candidates.append((title[:140], full))

        # Fallback: if the H3 pairing produced nothing, scan generic
        # article-shaped slugs (no nested path, not a section index).
        if not candidates:
            section_slugs = {
                "", "cy", "event-info", "charity", "our-community",
                "news-and-media", "r4w-shop", "privacy-policy",
                "make-your-mark", "vip-fundraiser-benefits",
                "disability-entry-accessibility", "get-race-ready-fast",
            }
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 14:
                    continue
                full = href if href.startswith("http") else _BASE + href
                if "cardiffhalfmarathon.co.uk" not in full:
                    continue
                tail = full.split("cardiffhalfmarathon.co.uk", 1)[-1].strip("/")
                if not tail or "/" in tail or tail in section_slugs:
                    continue
                if full in seen:
                    continue
                seen.add(full)
                candidates.append((text[:140], full))

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
