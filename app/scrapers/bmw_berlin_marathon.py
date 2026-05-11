"""BMW BERLIN-MARATHON — https://www.bmw-berlin-marathon.com/en/.

Deep scraper. Pulls homepage edition; sponsor logos from /en/sponsoren-partner;
news titles from /en/news-media/news; men's + women's podium and participant
count from the 2025 recap article. SCC EVENTS GmbH; first run 13 Oct 1974;
2020 cancelled, so 2026 is the 51st edition.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.bmw-berlin-marathon.com"

_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+BMW\s+BERLIN[\s\-]?MARATHON", re.I)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\b")

_COUNTRY_TO_ISO = {
    "Kenya": "KEN", "Ethiopia": "ETH", "Uganda": "UGA", "Tanzania": "TAN",
    "Japan": "JPN", "China": "CHN", "Germany": "GER", "France": "FRA",
    "Italy": "ITA", "Spain": "ESP", "Portugal": "POR", "Netherlands": "NED",
    "Eritrea": "ERI", "Bahrain": "BRN", "Israel": "ISR", "Switzerland": "SUI",
    "Great Britain": "GBR", "United States": "USA", "USA": "USA",
    "South Africa": "RSA", "Australia": "AUS", "Canada": "CAN",
    "Norway": "NOR", "Sweden": "SWE", "Morocco": "MAR", "Belgium": "BEL",
    "Poland": "POL",
}
_NATIONALITY_ADJ_TO_ISO = {
    "Kenyan": "KEN", "Ethiopian": "ETH", "Ugandan": "UGA", "Tanzanian": "TAN",
    "Japanese": "JPN", "Chinese": "CHN", "German": "GER", "French": "FRA",
    "Italian": "ITA", "Spanish": "ESP", "Portuguese": "POR", "Dutch": "NED",
    "Eritrean": "ERI", "Bahraini": "BRN", "Israeli": "ISR", "Swiss": "SUI",
    "British": "GBR", "American": "USA", "South African": "RSA",
    "Australian": "AUS", "Canadian": "CAN", "Norwegian": "NOR",
    "Swedish": "SWE", "Moroccan": "MAR", "Belgian": "BEL", "Polish": "POL"}
_COUNTRY_ALT = "|".join(re.escape(k) for k in _COUNTRY_TO_ISO)
_ADJ_ALT = "|".join(re.escape(k) for k in _NATIONALITY_ADJ_TO_ISO)

# Recap copy patterns: "Akira Akasaki of Japan", "Ethiopia's Chimdessa Debele",
# "Kenyan Sabastian Sawe", "Sabastian Sawe won the BMW BERLIN MARATHON".
_NAME_OF_COUNTRY_RE = re.compile(
    rf"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){{1,3}})\s+of\s+({_COUNTRY_ALT})"
)
_COUNTRYS_NAME_RE = re.compile(
    rf"({_COUNTRY_ALT})['’]s\s+([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){{1,3}})"
)
_ADJ_NAME_RE = re.compile(
    rf"\b({_ADJ_ALT})\s+([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){{1,3}})"
)
_WINNER_RE = re.compile(
    r"(?:^|[\.\!\?\n]|(?<=[a-z])\s)"
    r"([A-Z][\w'’\-]+\s+[A-Z][\w'’\-]+)\s+won\s+the\s+BMW\s+BERLIN[\s\-]?MARATHON",
)
_PODIUM_LINE_RE = re.compile(
    rf"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){{1,3}})\s*"
    rf"(?:\(({_COUNTRY_ALT})\)|,\s*({_COUNTRY_ALT}))"
    rf"[\s\-–:]*?(\d{{1,2}}:\d{{2}}:\d{{2}})"
)

# Trim recap at the first historical reference so a prior CR (e.g. Kipchoge
# 2022, 2:01:09) can't bleed into the live podium.
_RECORD_CONTEXT_RE = re.compile(
    r"course\s+record\s+set\s+by|previous\s+record|record\s+holder|"
    r"set\s+in\s+(?:19|20)\d{2}|in\s+(?:19|20)\d{2}\s*\(\d",
    re.I,
)
_HISTORICAL_RE = re.compile(
    r"\b(?:in|from|set\s+in|back\s+in|since)\s+(?:19|20)\d{2}\b", re.I
)

_KNOWN_BRANDS = [
    "BMW", "adidas", "Abbott", "Zalando", "Generali", "Brita", "Clif",
    "Erdinger", "Revolut", "Shokz", "Norqain", "Biotherm", "Blackroll",
    "Maurten", "Vilsa", "Ugreen", "Super Sparrow", "Höffner", "Hoeffner",
    "Chiquita", "Tagesspiegel", "Sportografen", "Realbuzz"]


@register("bmw-berlin-marathon")
class BMWBerlinMarathonScraper(BaseScraper):
    official_url = "https://www.bmw-berlin-marathon.com/en/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="SCC EVENTS GmbH",
            inception_year=1974,
            title_sponsor="BMW",
        )

        home = self.get(self.official_url)
        scraped_edition: Optional[int] = None
        if home is not None:
            text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(text)
            if m:
                try:
                    scraped_edition = int(m.group(1))
                except ValueError:
                    pass
        # 2026 = 51st running. Prefer the homepage value only if it's
        # already advanced past the canonical (heritage pages keep the
        # last-edition "50th" branding for months).
        canonical_2026 = 51
        facts.edition = (
            scraped_edition if scraped_edition and scraped_edition >= canonical_2026
            else canonical_2026
        )

        self._extract_sponsors(facts)
        recap_url = self._extract_news(facts)
        if recap_url:
            self._extract_recap(recap_url, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(urljoin(_BASE, "/en/sponsoren-partner/sponsors-partners"))
        if soup is None:
            return
        seen: set[str] = set()
        ordered: List[str] = []
        for img in soup.find_all("img"):
            haystack = (
                (img.get("alt") or "") + " "
                + (img.get("src") or "").rsplit("/", 1)[-1]
            ).lower()
            for brand in _KNOWN_BRANDS:
                if brand.lower() not in haystack:
                    continue
                canonical = "Höffner" if brand == "Hoeffner" else (
                    "Erdinger Alkoholfrei" if brand == "Erdinger" else brand
                )
                if canonical in seen:
                    break
                seen.add(canonical)
                ordered.append(canonical)
                break
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_news(self, facts: RaceFacts) -> Optional[str]:
        soup = self.get(urljoin(_BASE, "/en/news-media/news"))
        if soup is None:
            return None
        seen: set[str] = set()
        items: List[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news-media/news/detail/" not in href:
                continue
            full = href if href.startswith("http") else urljoin(_BASE, href)
            if full in seen:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 10:
                continue
            seen.add(full)
            items.append((title[:140], full))

        recap_url: Optional[str] = None
        for title, href in items:
            tlow = title.lower()
            if (
                ("sawe" in tlow and "world lead" in tlow)
                or "world lead at the bmw berlin" in tlow
                or "winner" in tlow
            ):
                recap_url = href
                break
        if recap_url:
            items.sort(key=lambda c: 0 if c[1] == recap_url else 1)
        for title, href in items[:5]:
            facts.highlights.append((title, href))
        return recap_url

    # ------------------------------------------------------------------
    def _extract_recap(self, recap_url: str, facts: RaceFacts) -> None:
        soup = self.get(recap_url)
        if soup is None:
            return
        for t in soup(["nav", "header", "footer", "script", "style", "aside"]):
            t.decompose()
        text = soup.get_text("\n", strip=True)
        idx = text.lower().find("sabastian sawe runs world lead")
        if idx == -1:
            for kw in ("won the bmw berlin marathon", "won the bmw berlin-marathon"):
                idx = text.lower().find(kw)
                if idx != -1:
                    break
        if idx == -1:
            idx = 0
        body = text[idx: idx + 8000]

        # Prefer the marathon-only count: "Among runners alone, 55,146
        # people will take part." That's the precise number registered
        # for the marathon distance, not the all-event "almost 80,000
        # participants" headline (which includes 5K, mini-marathon,
        # wheelchair, handcycle and inline skater starts).
        runners_only = re.search(
            r"(?:among\s+runners\s+alone|runners?\s+alone)\s*[,:]?\s*"
            r"([\d,.]{4,8})\s+(?:people|runners?)\s+(?:will\s+take\s+part|finished|crossed)",
            body,
            re.I,
        )
        if runners_only:
            raw = runners_only.group(1).replace(",", "").replace(".", "")
            try:
                n = int(raw)
                if 10_000 <= n <= 100_000:
                    facts.finishers_total = n
            except ValueError:
                pass

        if facts.finishers_total is None:
            m = re.search(
                r"(?:almost|approximately|over|nearly|some)?\s*"
                r"([\d,.]{4,7})\s+(?:people|runners|finishers|participants)",
                body,
                re.I,
            )
            if m:
                raw = m.group(1).replace(",", "").replace(".", "")
                try:
                    n = int(raw)
                    if 1000 <= n <= 200000:
                        facts.finishers_total = n
                except ValueError:
                    pass

        # Split men's vs women's by sentence-level cue.
        women_marker = re.search(
            r"(?:close finish|in the women['’]s race|women['’]s race)", body, re.I
        )
        if women_marker:
            men_text = body[: women_marker.start()]
            women_text = body[women_marker.start():]
        else:
            men_text, women_text = body, ""

        facts.mens_podium = self._parse_section(men_text)
        if women_text:
            facts.womens_podium = self._parse_section(women_text)

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_section(section: str) -> List[PodiumEntry]:
        if not section:
            return []
        end = len(section)
        for m in _RECORD_CONTEXT_RE.finditer(section):
            end = min(end, m.start())
        section = section[:end]

        candidates: List[Tuple[int, str, str]] = []
        for m in _NAME_OF_COUNTRY_RE.finditer(section):
            candidates.append((m.start(), m.group(1).strip(), _COUNTRY_TO_ISO.get(m.group(2), "")))
        for m in _COUNTRYS_NAME_RE.finditer(section):
            candidates.append((m.start(), m.group(2).strip(), _COUNTRY_TO_ISO.get(m.group(1), "")))
        for m in _ADJ_NAME_RE.finditer(section):
            candidates.append((m.start(), m.group(2).strip(), _NATIONALITY_ADJ_TO_ISO.get(m.group(1), "")))
        for m in _PODIUM_LINE_RE.finditer(section):
            country = m.group(2) or m.group(3) or ""
            candidates.append((m.start(), m.group(1).strip(), _COUNTRY_TO_ISO.get(country, "")))
        # Lead winner fallback: "<Name> won the BMW BERLIN MARATHON". Country
        # is inferred from the nearest "the <Adjective>" cue.
        for m in _WINNER_RE.finditer(section):
            window = section[max(0, m.start() - 200): m.end() + 600]
            adj_m = re.search(rf"\bthe\s+({_ADJ_ALT})\b", window)
            iso = _NATIONALITY_ADJ_TO_ISO.get(adj_m.group(1), "") if adj_m else ""
            candidates.append((m.start(), m.group(1).strip(), iso))

        candidates = sorted({(p, n, c) for p, n, c in candidates}, key=lambda x: x[0])

        times: List[Tuple[int, str]] = []
        for m in _TIME_RE.finditer(section):
            t = m.group(1)
            try:
                if int(t.split(":")[0]) < 2:
                    continue
            except ValueError:
                continue
            window = section[max(0, m.start() - 60): m.end() + 60]
            if _HISTORICAL_RE.search(window):
                continue
            times.append((m.start(), t))

        seen_names: set[str] = set()
        used_times: set[int] = set()
        entries: List[PodiumEntry] = []
        for pos, name, country in candidates:
            if name in seen_names:
                continue
            best = None
            best_d = 10**9
            for t_pos, t in times:
                if t_pos in used_times:
                    continue
                d = abs(t_pos - pos)
                if d < best_d:
                    best_d, best = d, (t_pos, t)
            if best is None or best_d > 120:
                continue
            seen_names.add(name)
            used_times.add(best[0])
            entries.append(PodiumEntry(rank=len(entries) + 1, name=name, nationality=country, timing=best[1]))
            if len(entries) == 3:
                break
        return entries
