"""BYD Singapore International Marathon presented by adidas — https://singaporemarathon.com/

Race ID references the new (2026) sponsor stack: BYD as title and adidas
as presenting partner. The official site at the time of this scrape still
runs under the "Standard Chartered Singapore Marathon" branding (the SCSM
era began in 2002), so most copy and sponsor logos surface SCSM. We pin
title_sponsor to "BYD" per the race ID and keep adidas alongside the
other sponsors so the report's branding line stays accurate.

Pulls:
  - /community/sponsors/  -> sponsor roster
  - /community/news/      -> top recent news titles + URLs
  - /community/history/   -> edition / inception fallback
  - /community/about-us/  -> organizer line + about overview

Note on hosts: singaporemarathon.com 301-redirects to www.singaporemarathon.com.
Setting official_url to the apex lets the subdomain match in BaseScraper
cover www. and any future subdomain.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Substring of either img alt text, src filename, or anchor text -> clean
# brand name. Title sponsors deliberately omitted from the map; we set
# them directly on facts. Order roughly follows tier seniority.
_LOGO_TOKEN_MAP: list[tuple[str, str]] = [
    ("byd", "BYD"),
    ("adidas", "adidas"),
    ("standard chartered", "Standard Chartered"),
    ("scbank", "Standard Chartered"),
    ("sport singapore", "Sport Singapore"),
    ("sportsg", "Sport Singapore"),
    ("singapore tourism", "Singapore Tourism Board"),
    ("stb", "Singapore Tourism Board"),
    ("ironman", "IRONMAN Group"),
    ("100 plus", "100PLUS"),
    ("100plus", "100PLUS"),
    ("seiko", "Seiko"),
    ("samsung", "Samsung"),
    ("tcs", "Tata Consultancy Services"),
    ("tata consultancy", "Tata Consultancy Services"),
    ("viewqwest", "ViewQwest"),
    ("ethiopian airlines", "Ethiopian Airlines"),
    ("joyvio", "Joyvio"),
    ("westin", "The Westin Singapore"),
    ("oatside", "OATSIDE"),
    ("fitness first", "Fitness First"),
    ("2nu", "2NU"),
    ("grab", "Grab"),
    ("running department", "The Running Department"),
    ("coached", "Coached"),
    ("puma", "PUMA"),
]

_NEWS_KEYWORDS = (
    "marathon", "scsm", "singapore", "runner", "course",
    "padang", "elite", "registration", "route", "byd", "adidas",
    "half", "finish",
)

@register("byd-singapore-international-marathon-presented-by-adidas")
class SingaporeMarathonScraper(BaseScraper):
    official_url = "https://singaporemarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="The IRONMAN Group (Singapore International Marathon Organising Committee)",
            title_sponsor="BYD",
            edition=25,             # SCSM/Singapore-Marathon era 1st = 2002 -> 2026 = 25th
            inception_year=2002,
            notes=(
                "2026 race not yet held; podium data unavailable. "
                "Brand transitioning from Standard Chartered to BYD/adidas for 2026."
            ),
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_history(facts)
        self._extract_about_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get("http://www.singaporemarathon.com/community/sponsors/")
        if soup is None:
            soup = self.get("https://singaporemarathon.com/community/sponsors/")
        if soup is None:
            return
        seen: set[str] = set()
        ordered: List[str] = []
        # Walk both <img> elements (alt + src) and any anchor text — the
        # SCSM site uses SVG placeholders for several logos so the brand
        # name often only lives in alt text or surrounding anchor copy.
        haystacks: List[str] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            src = (img.get("src") or "").lower()
            haystacks.append(alt + " " + src.rsplit("/", 1)[-1])
        for a in soup.find_all("a"):
            txt = a.get_text(" ", strip=True).lower()
            if 2 < len(txt) < 80:
                haystacks.append(txt)
        for h in haystacks:
            for needle, brand in _LOGO_TOKEN_MAP:
                if needle in h and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        # Title sponsor lives separately; drop it from "others".
        others = [b for b in ordered if b.lower() not in {"byd"}]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("http://www.singaporemarathon.com/community/news/")
        if soup is None:
            soup = self.get("https://singaporemarathon.com/community/news/")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: List[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 18 or len(text) > 240:
                continue
            full = href if href.startswith("http") else (
                "https://singaporemarathon.com" + href
            )
            if "singaporemarathon.com" not in full:
                continue
            if full in seen:
                continue
            # Skip the news index, category pages, and pagination.
            tail = full.rstrip("/").rsplit("/", 1)[-1]
            if tail in {"news", "community", "community-news"} or tail.startswith("page"):
                continue
            if "/category/" in full or "#" in full.split("/")[-1]:
                continue
            if len(tail) < 18:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _NEWS_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:200], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _extract_about_stats(self, facts: RaceFacts) -> None:
        """The /community/about-us/ page surfaces "over 50,000 local
        and international runners annually". We use that as a finisher
        proxy when nothing else is available, and look for spectator /
        volunteer / prize blurbs that occasionally appear in news
        listings on /community/news/."""
        import re as _re

        for url in (
            "http://www.singaporemarathon.com/community/about-us/",
            "https://singaporemarathon.com/community/about-us/",
            "http://www.singaporemarathon.com/community/news/",
            "https://singaporemarathon.com/community/news/",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)

            if facts.finishers_total is None:
                for pat in (
                    r"(?:over|more\s+than)\s+([\d,]{4,7})\s+(?:local\s+and\s+international\s+)?(?:runners|finishers|participants)",
                    r"([\d,]{4,7})\s+runners\s+in\s+sold[- ]out",
                ):
                    m = _re.search(pat, text, _re.I)
                    if m:
                        try:
                            n = int(m.group(1).replace(",", ""))
                        except ValueError:
                            continue
                        if 5_000 <= n <= 200_000:
                            facts.finishers_total = n
                            break

            if facts.prize_money_usd is None:
                m = _re.search(
                    r"(?:total\s+)?prize\s+(?:purse|money|pool|fund)\s*(?:of)?\s*"
                    r"(?:USD|US\$|\$|S\$|SGD)\s*([\d,]{4,9})",
                    text,
                    _re.I,
                )
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                        if 30_000 <= n <= 5_000_000:
                            # Treat S$ values as ~0.74 USD when the prefix
                            # is SGD/S$; otherwise take the figure as-is.
                            ctx = text[max(0, m.start() - 40): m.end()].lower()
                            if "s$" in ctx or "sgd" in ctx:
                                n = int(round(n * 0.74))
                            facts.prize_money_usd = n
                    except ValueError:
                        pass

            if facts.spectators is None:
                sm = _re.search(r"([\d,]{3,7})\s*\+?\s+spectators", text, _re.I)
                if sm:
                    try:
                        n = int(sm.group(1).replace(",", ""))
                        if 1_000 <= n <= 5_000_000:
                            facts.spectators = n
                    except ValueError:
                        pass

            if facts.volunteers is None:
                vm = _re.search(r"([\d,]{3,5})\s+volunteers", text, _re.I)
                if vm:
                    try:
                        n = int(vm.group(1).replace(",", ""))
                        if 100 <= n <= 50_000:
                            facts.volunteers = n
                    except ValueError:
                        pass

    # ------------------------------------------------------------------
    def _extract_history(self, facts: RaceFacts) -> None:
        # The history page is a long timeline that mentions many ordinal
        # editions ("19th edition", "1st edition") in passing. Rather than
        # try to find the "current edition" sentence — which the page
        # doesn't reliably print — we keep the hardcoded edition derived
        # from inception_year and only touch the page to confirm it's
        # reachable (and to surface a 404 in logs if the path moves).
        self.get("http://www.singaporemarathon.com/community/history/")
