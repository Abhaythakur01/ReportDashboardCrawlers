"""Schneider Electric Marathon de Paris — https://www.schneiderelectricparismarathon.com/

Deep scraper. The site has structured news articles per edition; the
race recap follows a consistent template ("X crossed the finish line ...
in 2h05'18 ... ahead of Y (2h05'23) and Z (2h05'28)") that's easy to
parse with a focused regex.

Pulls:
  - /en/event/partners → full sponsor list (img alts are clean)
  - /en/event/news     → 5 latest article headlines + URLs
  - dedicated recap article (auto-detected) → men's & women's podium
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Times appear as "2h05'18" or "2h05'18s" in copy. Normalise to H:MM:SS.
_PARIS_TIME_RE = re.compile(r"\b(\d{1,2})\s*h\s*(\d{2})\s*[’′'`]\s*(\d{2})\b")
_NAME_OF_COUNTRY_RE = re.compile(
    r"([A-Z][\wÀ-ÿ'’\-]{2,}(?:\s+[A-Z][\wÀ-ÿ'’\-]{2,}){0,3})"
    r"\s*\((\d{1,2})\s*h\s*(\d{2})\s*[’′'`]\s*(\d{2})\)"
)
_COUNTRY_HINT_RE = re.compile(
    r"(Italy|Italian|Ethiopia|Ethiopian|Kenya|Kenyan|Uganda|Ugandan|Tanzania|Tanzanian|"
    r"France|French|Germany|German|United States|American|Spain|Spanish|"
    r"Netherlands|Dutch|Great Britain|British|Morocco|Moroccan|Eritrea|Eritrean|"
    r"Bahrain|Bahraini|Israel|Israeli|Japan|Japanese|China|Chinese|Portugal|Portuguese|"
    r"South Africa|South African|Australia|Australian|Canada|Canadian|Sweden|Swedish|"
    r"Norway|Norwegian)"
)
_COUNTRY_TO_ISO = {
    "Italy": "ITA", "Italian": "ITA", "Ethiopia": "ETH", "Ethiopian": "ETH",
    "Kenya": "KEN", "Kenyan": "KEN", "Uganda": "UGA", "Ugandan": "UGA",
    "Tanzania": "TAN", "Tanzanian": "TAN", "France": "FRA", "French": "FRA",
    "Germany": "GER", "German": "GER", "United States": "USA", "American": "USA",
    "Spain": "ESP", "Spanish": "ESP", "Netherlands": "NED", "Dutch": "NED",
    "Great Britain": "GBR", "British": "GBR", "Morocco": "MAR", "Moroccan": "MAR",
    "Eritrea": "ERI", "Eritrean": "ERI", "Bahrain": "BRN", "Bahraini": "BRN",
    "Israel": "ISR", "Israeli": "ISR", "Japan": "JPN", "Japanese": "JPN",
    "China": "CHN", "Chinese": "CHN", "Portugal": "POR", "Portuguese": "POR",
    "South Africa": "RSA", "South African": "RSA", "Australia": "AUS", "Australian": "AUS",
    "Canada": "CAN", "Canadian": "CAN", "Sweden": "SWE", "Swedish": "SWE",
    "Norway": "NOR", "Norwegian": "NOR",
}


@register("schneider-electric-marathon-de-paris")
class SchneiderParisScraper(BaseScraper):
    official_url = "https://www.schneiderelectricparismarathon.com/en"

    def scrape(self) -> RaceFacts:
        base_origin = "https://www.schneiderelectricparismarathon.com"

        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Amaury Sport Organisation (A.S.O.)",
            title_sponsor="Schneider Electric",
        )

        # --- 1. News listing for highlights + recap discovery ---
        news_soup = self.get(base_origin + "/en/event/news")
        recap_url: str | None = None
        if news_soup is not None:
            for a in news_soup.select("a[href*='/news/']"):
                href = a.get("href", "")
                title = a.get_text(" ", strip=True)
                if "/news/" not in href:
                    continue
                # Trim newsflash timestamp prefix the site embeds
                clean_title = re.sub(r"^Newsflashes\s*\d{1,2}/\d{1,2}\s*-\s*\d{1,2}:\d{2}", "", title).strip()
                if not clean_title:
                    continue
                full_href = href if href.startswith("http") else base_origin + href
                if recap_url is None and ("light up" in clean_title.lower() or "winners" in clean_title.lower()):
                    recap_url = full_href
                if len(facts.highlights) < 5:
                    facts.highlights.append((clean_title[:120], full_href))

        # --- 2. Recap article: edition, finishers, podium ---
        recap_soup = self.get(recap_url) if recap_url else None
        text = ""
        if recap_soup is not None:
            text = " ".join(p.get_text(" ", strip=True) for p in recap_soup.find_all("p"))

        if not text:
            # Fallback: try the "57,464 hearts beating as one" stats article
            for title, url in facts.highlights:
                if "hearts beating" in title.lower():
                    s = self.get(url)
                    if s is not None:
                        text = " ".join(p.get_text(" ", strip=True) for p in s.find_all("p"))
                        break

        if text:
            self._extract_podium(text, facts)
            self._extract_meta(text, facts)

        # Fetch the stats article for finisher/spectator numbers (often
        # only present there).
        for title, url in facts.highlights:
            if "hearts beating" in title.lower() and url != recap_url:
                stats_soup = self.get(url)
                if stats_soup is not None:
                    stats_text = " ".join(p.get_text(" ", strip=True) for p in stats_soup.find_all("p"))
                    self._extract_meta(stats_text, facts)
                break

        # --- 3. Partners page: sponsor list ---
        partners_soup = self.get(base_origin + "/en/event/partners")
        if partners_soup is not None:
            seen: set[str] = set()
            sponsors: List[str] = []
            for img in partners_soup.find_all("img"):
                alt = (img.get("alt") or "").strip()
                if not alt or len(alt) > 60:
                    continue
                # Site prefixes alt with "Partner ..."
                if alt.lower().startswith("partner "):
                    name = alt[8:].strip()
                else:
                    continue
                # Skip generic / category placeholders
                if name.lower() in {"", "marathon de paris", "logo"}:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                sponsors.append(name)
            if sponsors:
                # Title sponsor is Schneider Electric — already set; remove from list
                others = [s for s in sponsors if s.lower() != "schneider electric"]
                facts.other_sponsors = "\n".join(others)

        return facts

    # ------------------------------------------------------------------
    def _extract_meta(self, text: str, facts: RaceFacts) -> None:
        # Edition: "49th edition"
        m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+edition", text, re.I)
        if m:
            facts.edition = int(m.group(1))
            facts.inception_year = (datetime.now().year - facts.edition + 1)

        # Finishers: "exactly 57,464 runners completed"
        m = re.search(r"(\d{1,3}(?:,\d{3})+)\s+runners\s+completed", text, re.I)
        if m:
            facts.finishers_total = int(m.group(1).replace(",", ""))

        # Spectators: "Nearly 200,000 spectators"
        m = re.search(r"(?:nearly|approximately|about)?\s*(\d{1,3}(?:,\d{3})+|\d+)\s+spectators", text, re.I)
        if m:
            facts.spectators = int(m.group(1).replace(",", ""))

        # Women%: "33% women"
        m = re.search(r"(\d{1,2})%\s+women", text, re.I)
        if m:
            facts.finishers_women_pct = float(m.group(1))
            facts.finishers_men_pct = 100.0 - facts.finishers_women_pct

        # International %: "29% international participants"
        # (recorded in notes for provenance; no dedicated facts field).
        m_intl = re.search(r"(\d{1,2})%\s+international", text, re.I)
        if m_intl and "international" not in facts.notes.lower():
            note = f"{m_intl.group(1)}% international participants"
            facts.notes = (facts.notes + " | " + note) if facts.notes else note

    def _extract_podium(self, text: str, facts: RaceFacts) -> None:
        """Paris recaps consistently follow:

            "<Italian/Ethiopian/...> <Name> crossed the finish line ... 2h05'18 ...
             winning ahead of <Country>'s <Name> (2h05'23) and <Country>'s
             <Name> (2h05'28)"

        for men, then a similar block for women anchored on a different
        sentence. We split the text by an uppercase-name anchor and parse
        each gender section.
        """
        # Approximate split: men's section ends, women's begins around the
        # phrase "women's course record" or "women's race".
        lower = text.lower()
        women_idx = -1
        for key in (
            "women's course record", "women’s course record",
            "the women's race", "the women’s race",
            "women's race", "women’s race",
            "shure demise under",  # specific to 2026 Paris but harmless if absent
        ):
            i = lower.find(key)
            if i != -1:
                women_idx = i if women_idx == -1 else min(women_idx, i)
        if women_idx == -1:
            men_text, women_text = text, ""
        else:
            men_text, women_text = text[:women_idx], text[women_idx:]

        facts.mens_podium = self._podium_from(men_text, gender="men")
        facts.womens_podium = self._podium_from(women_text, gender="women")

    # Runner-up pattern with EXPLICIT preceding country: "Ethiopia's Name (time)"
    _COUNTRYS_NAME_TIME_RE = re.compile(
        r"(Italy|Ethiopia|Kenya|Uganda|Tanzania|France|Germany|United States|"
        r"Spain|Netherlands|Great Britain|Morocco|Eritrea|Bahrain|Israel|Japan|"
        r"China|Portugal|South Africa|Australia|Canada|Sweden|Norway)['’]s\s+"
        r"([A-Z][\wÀ-ÿ'’\-]{2,}(?:\s+[A-Z][\wÀ-ÿ'’\-]{2,}){0,3})"
        r"\s*\((\d{1,2})\s*h\s*(\d{2})\s*[’′'`]\s*(\d{2})\)"
    )
    # "her compatriot <Name> (time)" — same nationality as previous athlete
    _COMPATRIOT_NAME_TIME_RE = re.compile(
        r"compatriot\s+"
        r"([A-Z][\wÀ-ÿ'’\-]{2,}(?:\s+[A-Z][\wÀ-ÿ'’\-]{2,}){0,3})"
        r"\s*\((\d{1,2})\s*h\s*(\d{2})\s*[’′'`]\s*(\d{2})\)"
    )

    def _podium_from(self, section: str, gender: str) -> List[PodiumEntry]:
        if not section:
            return []
        entries: List[PodiumEntry] = []

        # Winner: the first H:MM:SS-ish time in the section, paired with the
        # nearest preceding name introduced by "<Country>'s <Name>" or
        # "the <Adjective> <Name>".
        winner_time_match = _PARIS_TIME_RE.search(section)
        if winner_time_match:
            t = self._fmt_time(winner_time_match)
            ctx = section[max(0, winner_time_match.start() - 250): winner_time_match.start()]
            name, country = self._winner_name_from_ctx(ctx)
            if name:
                entries.append(PodiumEntry(rank=1, name=name, nationality=country, timing=t))

        # Runners-up: collect (position, name, country, time) candidates from
        # both explicit country-prefixed mentions AND compatriot mentions,
        # sort by document order, dedupe.
        candidates: list[tuple[int, str, str, str]] = []
        for m in self._COUNTRYS_NAME_TIME_RE.finditer(section):
            if self._is_historical_context(section, m.start()):
                continue
            country_full = m.group(1)
            name = m.group(2).strip()
            t = f"{int(m.group(3))}:{m.group(4)}:{m.group(5)}"
            candidates.append((m.start(), name, _COUNTRY_TO_ISO.get(country_full, ""), t))
        for m in self._COMPATRIOT_NAME_TIME_RE.finditer(section):
            if self._is_historical_context(section, m.start()):
                continue
            name = m.group(1).strip()
            t = f"{int(m.group(2))}:{m.group(3)}:{m.group(4)}"
            country = entries[0].nationality if entries else ""
            candidates.append((m.start(), name, country, t))
        candidates.sort(key=lambda c: c[0])

        seen_names = {p.name for p in entries}
        for _, name, country, t in candidates:
            if name in seen_names:
                continue
            seen_names.add(name)
            entries.append(PodiumEntry(rank=len(entries) + 1, name=name, nationality=country, timing=t))
            if len(entries) == 3:
                break
        return entries[:3]

    def _winner_name_from_ctx(self, ctx: str) -> tuple[str, str]:
        # Pattern A: "<Country>'s <Name>" — pick the LAST occurrence
        country_name_re = re.compile(
            r"(Italy|Ethiopia|Kenya|Uganda|Tanzania|France|Germany|United States|"
            r"Spain|Netherlands|Great Britain|Morocco|Eritrea|Bahrain|Israel|Japan|"
            r"China|Portugal|South Africa|Australia|Canada|Sweden|Norway)['’]s\s+"
            r"([A-Z][\wÀ-ÿ'’\-]{2,}(?:\s+[A-Z][\wÀ-ÿ'’\-]{2,}){0,3})"
        )
        matches = list(country_name_re.finditer(ctx))
        if matches:
            m = matches[-1]
            return m.group(2).strip(), _COUNTRY_TO_ISO.get(m.group(1), "")
        # Pattern B: "the <Adjective> <Name>" (e.g. "the Italian Yemaneberhan Crippa")
        adj_name_re = re.compile(
            r"\bthe\s+(Italian|Ethiopian|Kenyan|Ugandan|Tanzanian|French|German|"
            r"American|Spanish|Dutch|British|Moroccan|Eritrean|Bahraini|Israeli|"
            r"Japanese|Chinese|Portuguese|South African|Australian|Canadian|"
            r"Swedish|Norwegian)\s+"
            r"([A-Z][\wÀ-ÿ'’\-]{2,}(?:\s+[A-Z][\wÀ-ÿ'’\-]{2,}){0,3})"
        )
        matches = list(adj_name_re.finditer(ctx))
        if matches:
            m = matches[-1]
            return m.group(2).strip(), _COUNTRY_TO_ISO.get(m.group(1), "")
        return "", ""

    @staticmethod
    def _fmt_time(m) -> str:
        return f"{int(m.group(1))}:{m.group(2)}:{m.group(3)}"

    @staticmethod
    def _is_historical_context(text: str, pos: int) -> bool:
        """Skip mentions framed as a prior course record / set in some
        previous year (e.g. "held since 2022 by Kenya's Judith Korir")."""
        window = text[max(0, pos - 100): pos + 50].lower()
        return any(k in window for k in (
            "previous course record", "held since", "set in 20", "set in 19",
            "since 20", "course record (", "course record held",
        ))
