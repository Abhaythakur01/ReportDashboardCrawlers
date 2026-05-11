"""NLB Ljubljana Marathon — https://www.ljubljanskimaraton.si/en

30th edition on 2026-10-17/18 (race is run as a weekend with the Karst
warm-up, a half-marathon Generali ZAME, the Heineken 0.0 Marathon, the
Garmin 10 km, and the VITA kids' run sharing the umbrella name).

Title sponsor: NLB (Nova Ljubljanska Banka). Co-sponsors include
Generali ZAME (half), Heineken 0.0 (marathon), Garmin (10 km).

The marathon is in the future at scrape time, so podiums are usually
empty and the recap article only appears in October. Sponsor data is
stable on /en/sponsors and news index pages.

Pulls:
  - /en/sponsors → tier-grouped sponsor list (NLB / Diamond / Large /
                    Sponsors / Partners / Media)
  - /en/news     → highlights (recap if available)
  - homepage    → confirms upcoming-edition number when published

Note: the protocol redirects to ``http://`` on the bare host. Both
``https://www.ljubljanskimaraton.si`` and ``http://ljubljanskimaraton.si``
resolve to the same Slovenian IP, so we register the canonical
``https://`` form and let the BaseScraper handle the redirect target
(it stays on the same registrable domain).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.ljubljanskimaraton.si"

# Section headings on /en/sponsors → role tag.
_SPONSOR_SECTIONS = [
    ("main sponsor",        "title"),
    ("title sponsor",       "title"),
    ("organiser",           "organiser"),
    ("performer",           "skip"),
    ("diamond sponsors",    "diamond"),
    ("large sponsors",      "large"),
    ("sponsors of school",  "skip"),
    ("supporters",          "skip"),
    ("media sponsors",      "media"),
    ("partners",            "partner"),
    ("sponsors",            "sponsor"),
]

# Filename substring → clean brand name. Logo images on /en/sponsors
# don't carry alt text, so the filename is the only on-page identifier.
_LOGO_FILE_MAP: list[tuple[str, str]] = [
    ("mestna-obcina-ljubljana", "Mestna občina Ljubljana"),
    ("ljubljanajesport",        "Ljubljana je Sport"),
    ("timinglj",                "Timing Ljubljana"),
    ("logo_nlb",                "NLB"),
    ("generali",                "Generali ZAME"),
    ("intersport",              "Intersport"),
    ("sto_logo",                "Slovenian Tourist Board"),
    ("vw",                      "Volkswagen Slovenia"),
    ("powerade",                "Powerade"),
    ("enervit",                 "Enervit"),
    ("eurocom",                 "Eurocom"),
    ("garmin",                  "Garmin"),
    ("heineken",                "Heineken"),
    ("hoka",                    "HOKA"),
    ("lelosi",                  "Lelosi"),
    ("radenska",                "Radenska"),
    ("diasporal",               "Diasporal Magnesium"),
    ("duracell",                "Duracell"),
    ("cgp_energetikaljubljana", "CGP Energetika Ljubljana"),
    ("valens",                  "Valens Health"),
    ("border_gremo",            "Borger Gremo"),
    ("btc-city",                "BTC City"),
    ("easypark",                "EasyPark"),
    ("eusalogo",                "EUSA"),
    ("gr_2018",                 "GR Ljubljana Exhibition Centre"),
    ("jrl-logo",                "JRL"),
    ("knorr",                   "Knorr"),
    ("sz-grem-z-vlakom",        "Slovenian Railways"),
    ("logo_tl",                 "Visit Ljubljana"),
    ("co-funded-by-the-eu",     "European Commission"),
    ("logo-poptv",              "Pop TV"),
    ("val202",                  "Val 202"),
    ("mediabus",                "Mediabus"),
    ("siol",                    "SIOL.net"),
]


@register("nlb-ljubljana-marathon")
class LjubljanaMarathonScraper(BaseScraper):
    official_url = _BASE + "/en"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Mestna občina Ljubljana (City of Ljubljana)",
            title_sponsor="NLB (Nova Ljubljanska Banka)",
            inception_year=1996,
            edition=30,  # 2026 = 30th edition (1st = 1996)
        )

        self._extract_sponsors(facts)
        recap_url = self._extract_highlights(facts)
        self._verify_edition(facts)
        if recap_url:
            self._extract_recap_stats(recap_url, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_recap_stats(self, url: str, facts: RaceFacts) -> None:
        """Pull the marathon-distance finisher count from the recap.

        The 2025 NLB Ljubljana Marathon recap "The capital flooded with
        the most runners…" reports the Sunday breakdown as
        ``Marathon (42 km) — 2,832`` / ``Half (21 km) — 7,405`` / ``10
        km — 6,463``. We want the marathon row only (race_id =
        nlb-ljubljana-marathon).
        """
        soup = self.get(url)
        if soup is None:
            return
        body = soup.find("article") or soup.find("main") or soup
        text = body.get_text(" ", strip=True)
        # The recap renders the marathon row as
        # ``42 km (marathon): 3,310 (registered), 2,871 (at the start),
        # 2,832 (at the finish)``. We want the finish-line number.
        m = re.search(
            r"42\s*km[^:]{0,20}:.{0,140}?(\d{1,2}[, ]?\d{3})\s*\(at\s+the\s+finish\)",
            text,
            re.I,
        )
        if m and facts.finishers_total is None:
            try:
                v = int(m.group(1).replace(",", "").replace(" ", ""))
                if 1000 <= v <= 50000:
                    facts.finishers_total = v
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/en/sponsors")
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[str] = []
        current_role: str = ""

        for el in soup.find_all(["h1", "h2", "h3", "h4", "img"]):
            if el.name in {"h1", "h2", "h3", "h4"}:
                low = el.get_text(" ", strip=True).lower().strip()
                # Match longest needle first.
                current_role = ""
                for needle, role in _SPONSOR_SECTIONS:
                    if low.startswith(needle):
                        current_role = role
                        break
                continue
            if not current_role or current_role == "skip":
                continue
            src = (el.get("src") or "").lower().rsplit("/", 1)[-1]
            if not src:
                continue
            brand: Optional[str] = None
            for needle, label in _LOGO_FILE_MAP:
                if needle in src:
                    brand = label
                    break
            if brand is None:
                continue
            key = brand.lower()
            if key in seen:
                continue
            seen.add(key)
            if current_role == "title":
                # Already in facts.title_sponsor.
                continue
            ordered.append(brand)

        if ordered:
            facts.other_sponsors = "\n".join(ordered[:30])

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        # The default /en/news index only shows the latest articles; the
        # post-race recap from October 2025 lives on /en/news/2025.
        # Aggregate links from both pages so the recap is reachable.
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for path in ("/en/news", "/en/news/2025"):
            soup = self.get(_BASE + path)
            if soup is None:
                continue
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 14 or text.lower().startswith("read"):
                    continue
                if "/news/" not in href:
                    continue
                full = href if href.startswith("http") else _BASE + href
                if full in seen:
                    continue
                # Strip leading "DD. M. YYYY" or "DD. M. YYYY, SECTION NAME"
                # prefix and trailing " Read" suffix added by the news-card
                # template (the section tag is uppercase: "SPONSORSHIP NEWS").
                cleaned = re.sub(
                    r"^\d{1,2}\.\s*\d{1,2}\.\s*\d{4}\s*",
                    "",
                    text,
                ).strip()
                # Drop the optional ", SECTION TAG" qualifier (e.g.
                # ", SPONSORSHIP NEWS"). The tag is one or more all-caps
                # words; we eat the comma and the run of caps tokens.
                cleaned = re.sub(
                    r"^,\s*(?:[A-Z]+\s+){1,4}",
                    "",
                    cleaned,
                ).strip()
                cleaned = re.sub(r"\s+Read\s*$", "", cleaned).strip()
                if len(cleaned) < 8:
                    cleaned = text
                seen.add(full)
                candidates.append((cleaned[:140], full))

        # Lift any post-race recap to the top. Strong-recap keys (the
        # article that quotes finisher counts) take priority over the
        # weaker keyword set ("growing", "winners" and similar appear
        # in pre-event articles too).
        strong_recap_keys = ("capital flooded", "most runners", "victorious",
                             "shatter", "course record")
        weak_recap_keys = ("winner", "winners", "podium", "record",
                           "results", "recap", "ljubljana marathon is growing")

        def rank(c: Tuple[str, str]) -> int:
            low = c[0].lower()
            if any(k in low for k in strong_recap_keys):
                return 0
            if any(k in low for k in weak_recap_keys):
                return 1
            return 2

        candidates.sort(key=rank)
        recap_url: Optional[str] = None
        if candidates:
            top_title, top_url = candidates[0]
            if any(k in top_title.lower() for k in strong_recap_keys):
                recap_url = top_url
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
        return recap_url

    # ------------------------------------------------------------------
    def _verify_edition(self, facts: RaceFacts) -> None:
        """Try to read the upcoming-edition number off the homepage."""
        soup = self.get(self.official_url)
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+(?:NLB\s+)?Ljubljana\s+Marathon", text, re.I)
        if m:
            try:
                ed = int(m.group(1))
                if 1 <= ed <= 100:
                    facts.edition = ed
                    facts.inception_year = datetime.now().year - ed + 1
            except ValueError:
                pass
