"""ADNOC Abu Dhabi Marathon — https://www.adnocabudhabimarathon.com/en

The 2026 Abu Dhabi Marathon is the 9th edition (inaugural 2018), scheduled
for 2026-12-12. Title sponsor: ADNOC (Abu Dhabi National Oil Company).
Organising body: Abu Dhabi Sports Council.

The official site is a thin SPA-style landing built on top of a Njuko
registration backend; sub-pages like /en/about, /en/news, /en/sponsors
return 404. Static content is therefore limited to the homepage and a
handful of outbound links. The scraper:
  - reads the homepage to confirm the date / edition copy and pull any
    sponsor logos rendered server-side (img alt + src whitelist),
  - falls back to a hardcoded organizer + ADNOC title sponsor pairing,
  - leaves highlights blank when the news section isn't published yet
    (the homepage occasionally surfaces 1-2 news cards near the bottom).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Outbound host on the homepage -> clean partner name. Operational hosts
# (registration, results, social, app stores) are excluded.
_PARTNER_HOST_MAP: dict[str, str] = {
    "www.adnoc.ae":  "ADNOC",
    "www.adsc.ae":   "Abu Dhabi Sports Council",
    "adsc.ae":       "Abu Dhabi Sports Council",
}

_OPERATIONAL_HOST_FRAGMENTS = (
    "njuko.com", "raceresult.com", "facebook.com", "tiktok.com",
    "instagram.com", "twitter.com", "x.com", "youtube.com",
    "play.google.com", "apps.apple.com", "linkedin.com",
)

# Image alt / filename whitelist (lowercase substrings). Catches sponsor
# logos that render as <img> rather than outbound links.
_LOGO_TOKEN_MAP: list[tuple[str, str]] = [
    ("adnoc", "ADNOC"),
    ("abu dhabi sports council", "Abu Dhabi Sports Council"),
    ("adsc", "Abu Dhabi Sports Council"),
    ("department of culture", "Department of Culture and Tourism - Abu Dhabi"),
    ("dct", "Department of Culture and Tourism - Abu Dhabi"),
    ("experience abu dhabi", "Experience Abu Dhabi"),
    ("etihad", "Etihad Airways"),
    ("adidas", "adidas"),
    ("nike", "Nike"),
    ("asics", "ASICS"),
    ("garmin", "Garmin"),
    ("seiko", "Seiko"),
]

_EDITION_RE = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+edition", re.I)


@register("adnoc-abu-dhabi-marathon")
class AdnocAbuDhabiMarathonScraper(BaseScraper):
    official_url = "https://www.adnocabudhabimarathon.com/en"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Abu Dhabi Sports Council",
            title_sponsor="ADNOC (Abu Dhabi National Oil Company)",
            edition=9,             # 1st edition 2018 -> 2026 = 9th
            inception_year=2018,
            notes="Race scheduled 2026-12-12; podium data not yet available.",
        )

        self._extract_homepage(facts)
        return facts

    # ------------------------------------------------------------------
    def _apply_stat_regexes(self, text: str, facts: RaceFacts) -> None:
        if facts.finishers_total is None:
            for pat in (
                r"([\d,]{4,7})\s+(?:marathon\s+)?(?:finishers|runners|participants)",
                r"field\s+of\s+([\d,]{4,7})",
            ):
                m = re.search(pat, text, re.I)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                    except ValueError:
                        continue
                    if 1_000 <= n <= 100_000:
                        facts.finishers_total = n
                        break

        if facts.prize_money_usd is None:
            for pat in (
                r"prize\s+(?:purse|fund|pool|money)\s+(?:of\s+)?(?:USD|US\$|\$)\s*([\d,]{4,9})",
                r"(?:USD|US\$|\$)\s*([\d,]{4,9})\s+prize\s+(?:purse|fund|pool|money)",
                r"total\s+prize\s+(?:purse|fund|pool|money)\s*[:\-]?\s*(?:USD|US\$|\$)\s*([\d,]{4,9})",
            ):
                m = re.search(pat, text, re.I)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                    except ValueError:
                        continue
                    if 50_000 <= n <= 5_000_000:
                        facts.prize_money_usd = n
                        break

        if facts.spectators is None:
            sm = re.search(r"([\d,]{3,7})\s*\+?\s+spectators", text, re.I)
            if sm:
                try:
                    n = int(sm.group(1).replace(",", ""))
                    if 1_000 <= n <= 5_000_000:
                        facts.spectators = n
                except ValueError:
                    pass

        if facts.volunteers is None:
            vm = re.search(r"([\d,]{3,5})\s+volunteers", text, re.I)
            if vm:
                try:
                    n = int(vm.group(1).replace(",", ""))
                    if 100 <= n <= 50_000:
                        facts.volunteers = n
                except ValueError:
                    pass

        if facts.finishers_women_pct is None:
            wm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+women", text, re.I)
            if wm:
                try:
                    facts.finishers_women_pct = float(wm.group(1))
                except ValueError:
                    pass
        if facts.finishers_men_pct is None:
            mm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+men", text, re.I)
            if mm:
                try:
                    facts.finishers_men_pct = float(mm.group(1))
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    def _extract_homepage(self, facts: RaceFacts) -> None:
        # The homepage is the canonical and effectively only page. Try the
        # /en path first, then fall back to the apex (which rewrites to /en).
        soup = self.get("https://www.adnocabudhabimarathon.com/en")
        if soup is None:
            soup = self.get("https://www.adnocabudhabimarathon.com/")
        if soup is None:
            return

        text = soup.get_text(" ", strip=True)

        # Edition copy ("12th edition" / "9th edition"). Only override the
        # hardcoded value if it sits in a sane range.
        m = _EDITION_RE.search(text)
        if m:
            try:
                ed = int(m.group(1))
                if 5 <= ed <= 20:
                    facts.edition = ed
            except ValueError:
                pass

        # Sponsor / partner logos via outbound-host map.
        seen: set[str] = set()
        ordered: List[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            host = urlparse(href).netloc.lower()
            if any(frag in host for frag in _OPERATIONAL_HOST_FRAGMENTS):
                continue
            brand = _PARTNER_HOST_MAP.get(host)
            if brand and brand not in seen:
                seen.add(brand)
                ordered.append(brand)

        # Layer img alt / src whitelist on top — picks up logos that
        # aren't wrapped in outbound anchors.
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            src = (img.get("src") or "").lower()
            haystack = alt + " " + src.rsplit("/", 1)[-1]
            for needle, brand in _LOGO_TOKEN_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break

        # Drop the title sponsor and the organizer (already captured on
        # the relevant fields) from "other_sponsors".
        skip_keys = {
            "adnoc", "adnoc (abu dhabi national oil company)",
            "abu dhabi sports council",
        }
        others = [b for b in ordered if b.lower() not in skip_keys]
        if others:
            facts.other_sponsors = "\n".join(others)

        # Highlights: scrape any news-card anchors that resolve to in-origin
        # article paths. The site rarely exposes a /news listing, so this
        # is best-effort and often returns nothing.
        candidates: List[Tuple[str, str]] = []
        seen_urls: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            txt = a.get_text(" ", strip=True)
            if not txt or len(txt) < 18 or len(txt) > 240:
                continue
            full = href if href.startswith("http") else (
                "https://www.adnocabudhabimarathon.com" + href
            )
            if "adnocabudhabimarathon.com" not in full:
                continue
            tail = full.rstrip("/").rsplit("/", 1)[-1]
            if tail in {"en", "ar", ""} or len(tail) < 8:
                continue
            if any(frag in full for frag in ("/register", "/results", "raceresult")):
                continue
            if full in seen_urls:
                continue
            # Heuristic: news article slugs usually contain at least one dash
            # (multi-word slug) and aren't pure section names.
            if "-" not in tail:
                continue
            seen_urls.add(full)
            candidates.append((txt[:200], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

        # Run the stat regex sweep against the homepage text — picks up
        # by-the-numbers blurbs when the site publishes them.
        self._apply_stat_regexes(text, facts)
