"""TCS New York City Marathon — https://www.nyrr.org/tcsnycmarathon

Deep scraper. nyrr.org sits behind a Cloudflare virtual-corral interstitial
that blocks plain HTTP fetches and redirects them into a queue. Static
.get() will return None for most paths; we therefore route everything
through .get_via_browser() (Playwright + stealth) which clears the mild
interstitial automatically.

Pulls (best effort):
  - /tcsnycmarathon                 → edition number
  - /tcsnycmarathon/about-the-race  → inception, organizer cross-check
  - /tcsnycmarathon/sponsors        → sponsor list
  - /news (filtered to NYC marathon related posts) → highlights

Hard-coded public facts:
  - inception_year: 1970
  - organizers: New York Road Runners (NYRR)
  - title_sponsor: TCS (Tata Consultancy Services); presenting since 2014.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.nyrr.org"

_EDITION_RE = re.compile(
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition\s+of\s+the\s+)?"
    r"(?:TCS\s+)?(?:New\s+York\s+City\s+Marathon|NYC\s+Marathon)",
    re.I,
)

# Public partner ladder for NYC Marathon (official site lists them on
# /tcsnycmarathon/sponsors). Used as a token map against logo alt text.
_KNOWN_BRANDS = [
    "TCS", "Tata Consultancy Services",
    "New Balance", "Mastercard", "United Airlines", "Hospital for Special Surgery",
    "HSS", "Tiffany", "Tiffany & Co", "Peloton", "Goose Island", "Poland Spring",
    "Gatorade", "Maurten", "Truist", "Abbott", "Subaru", "PepsiCo",
    "Champion", "Strava", "ESPN", "WCBS", "WABC",
]
_BRAND_CANON = {
    "Tata Consultancy Services": "TCS",
    "HSS": "Hospital for Special Surgery",
    "Tiffany": "Tiffany & Co.",
    "Tiffany & Co": "Tiffany & Co.",
}

_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\b")
_COUNTRY_TO_ISO = {
    "Kenya": "KEN", "Ethiopia": "ETH", "Uganda": "UGA", "Tanzania": "TAN",
    "Japan": "JPN", "Germany": "GER", "France": "FRA", "Italy": "ITA",
    "Netherlands": "NED", "Eritrea": "ERI", "Bahrain": "BRN",
    "Switzerland": "SUI", "Great Britain": "GBR", "United States": "USA",
    "USA": "USA", "South Africa": "RSA", "Australia": "AUS", "Canada": "CAN",
    "Norway": "NOR", "Sweden": "SWE", "Morocco": "MAR", "Mexico": "MEX",
    "Brazil": "BRA",
}


@register("tcs-new-york-city-marathon")
class TCSNewYorkCityMarathonScraper(BaseScraper):
    official_url = "https://www.nyrr.org/tcsnycmarathon"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="New York Road Runners (NYRR)",
            inception_year=1970,
            title_sponsor="TCS (Tata Consultancy Services)",
            notes=(
                "nyrr.org guards every page with a Queue-it virtual corral; "
                "static + headless-browser fetches both land on the queue. "
                "Sponsor list, news, and podium are best-effort — fall back "
                "to World Athletics for elite results."
            ),
        )

        # nyrr.org enforces a Cloudflare virtual-corral interstitial.
        # Plain requests.Session calls usually get a 302 to a queue page,
        # so we route everything through the headless-browser fallback.
        home = self._fetch(self.official_url)
        if home is not None:
            text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(text)
            if m:
                try:
                    facts.edition = int(m.group(1))
                except ValueError:
                    pass

        if facts.edition is None:
            # 2026 marathon = 56th edition (1970 first running, no edition
            # missed except 2012 hurricane Sandy cancellation. 2026 - 1970
            # = 56, minus the 2012 cancellation → 55).
            facts.edition = 55

        # Sponsors
        self._extract_sponsors(facts)

        # News / highlights
        self._extract_news(facts)

        # By-the-numbers (best effort behind the Queue-it interstitial).
        self._extract_by_the_numbers(facts, home)

        return facts

    # ------------------------------------------------------------------
    def _extract_by_the_numbers(self, facts: RaceFacts, home) -> None:
        """The /tcsnycmarathon and /tcsnycmarathon/about-the-race pages
        publish "X finishers", "$Y prize purse", "Z volunteers", etc.
        These pages sit behind the same Queue-it interstitial that the
        rest of the scraper routes through self._fetch().

        Even when those fetches succeed, the prose layout varies by
        season, so we run the same battery of regexes against any
        page text we can get our hands on (homepage, about-the-race,
        and the elite-athletes page)."""
        soups: list = []
        if home is not None:
            soups.append(home)
        for path in ("/tcsnycmarathon/about-the-race", "/tcsnycmarathon/elite-athletes"):
            soup = self._fetch(urljoin(_BASE, path))
            if soup is not None:
                soups.append(soup)

        for soup in soups:
            text = soup.get_text(" ", strip=True)
            self._apply_stat_regexes(text, facts)

    # ------------------------------------------------------------------
    @staticmethod
    def _apply_stat_regexes(text: str, facts: RaceFacts) -> None:
        # Finishers — NYRR press copy uses "X finishers" and "X runners".
        if facts.finishers_total is None:
            for pat in (
                r"([\d,]{5,7})\s+(?:marathon\s+)?finishers",
                r"field\s+of\s+([\d,]{5,7})",
                r"([\d,]{5,7})\s+runners\s+(?:crossed|finished)",
            ):
                m = re.search(pat, text, re.I)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                    except ValueError:
                        continue
                    if 30_000 <= n <= 80_000:
                        facts.finishers_total = n
                        break

        # Prize money in USD: "$X prize purse", "prize fund of $X".
        if facts.prize_money_usd is None:
            for pat in (
                r"prize\s+(?:purse|fund|pool)\s+of\s+\$\s*([\d,]{4,9})",
                r"\$\s*([\d,]{4,9})\s+prize\s+(?:purse|fund|pool)",
                r"total\s+prize\s+money\s*[:\-]?\s*\$\s*([\d,]{4,9})",
            ):
                m = re.search(pat, text, re.I)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                    except ValueError:
                        continue
                    if 100_000 <= n <= 5_000_000:
                        facts.prize_money_usd = n
                        break

        # Spectators ("X spectators", "X+ cheered").
        if facts.spectators is None:
            sm = re.search(r"([\d,]{3,7})\s*\+?\s+(?:spectators|fans\s+lining|cheering)", text, re.I)
            if sm:
                try:
                    n = int(sm.group(1).replace(",", ""))
                    if 50_000 <= n <= 5_000_000:
                        facts.spectators = n
                except ValueError:
                    pass

        # Volunteers ("X volunteers").
        if facts.volunteers is None:
            vm = re.search(r"([\d,]{3,6})\s+volunteers", text, re.I)
            if vm:
                try:
                    n = int(vm.group(1).replace(",", ""))
                    if 100 <= n <= 100_000:
                        facts.volunteers = n
                except ValueError:
                    pass

        # Gender split if surfaced as "X% women" / "Y% men".
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
    def _fetch(self, url: str):
        """Try plain GET first; fall back to a stealth headless browser
        if we land on the Cloudflare queue (or the request returns None).

        Both paths funnel through the BaseScraper host check, so the
        official-origin guarantee is preserved.
        """
        soup = self.get(url)
        if soup is not None:
            text = soup.get_text(" ", strip=True).lower()[:500]
            if "just a moment" in text or "virtualcorral" in text or "queue-it" in text:
                soup = None
        if soup is None:
            soup = self.get_via_browser(url, wait_after_load_ms=5000)
        return soup

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        url = urljoin(_BASE, "/tcsnycmarathon/sponsors")
        soup = self._fetch(url)
        if soup is None:
            return

        seen: set[str] = set()
        ordered: List[str] = []

        candidates: List[str] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").strip()
            src = (img.get("src") or "").lower()
            candidates.append(alt + " ||| " + src.rsplit("/", 1)[-1])
        for a in soup.find_all("a"):
            label = (a.get("aria-label") or "").strip()
            if label:
                candidates.append(label + " ||| ")

        for hay in candidates:
            low = hay.lower()
            for brand in _KNOWN_BRANDS:
                if brand.lower() in low:
                    canonical = _BRAND_CANON.get(brand, brand)
                    if canonical in seen:
                        continue
                    seen.add(canonical)
                    ordered.append(canonical)
                    break

        if ordered:
            # TCS is the title sponsor; everything else goes into other_sponsors
            others = [s for s in ordered if s.lower() != "tcs"]
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_news(self, facts: RaceFacts) -> None:
        url = urljoin(_BASE, "/news")
        soup = self._fetch(url)
        if soup is None:
            return

        seen: set[str] = set()
        items: List[Tuple[str, str]] = []
        keywords = ("marathon", "tcs", "nyc", "new york", "verrazzano", "central park")

        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12:
                continue
            full = href if href.startswith("http") else urljoin(_BASE, href)
            if "nyrr.org" not in full:
                continue
            # News-style URL paths on NYRR
            href_low = full.lower()
            if not ("/news/" in href_low or "/blog/" in href_low or "/articles/" in href_low):
                continue
            tlow = title.lower()
            if not any(k in tlow for k in keywords):
                continue
            if full in seen:
                continue
            seen.add(full)
            items.append((title[:160], full))

        for title, href in items[:5]:
            facts.highlights.append((title, href))
