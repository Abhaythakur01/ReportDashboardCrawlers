"""TCS Amsterdam Marathon — https://www.tcsamsterdammarathon.nl/en/

51st edition scheduled for 2026-10-18. The 2025 race was the 50th edition
(run 2025-10-19), so 2026 is edition 51. Race is organised by Le Champion
and titled by Tata Consultancy Services (TCS); main sponsor is Mizuno.

The .nl host redirects to .eu for the homepage; ``requests`` follows
the redirect transparently. Sub-paths like /sponsors and /nieuws are
served directly under the .nl host, so they pass the official-host
check without issue.

Pulls:
  - /sponsors → cleanly tiered sponsor blocks (Titelsponsor / Hoofdsponsor /
    Co-sponsors / Sub-sponsors / Partners / Goede doelen / Aangesloten bij).
    Logos use generic ``alt="Logo"`` so the scraper maps each filename
    substring to a clean brand name.
  - / (homepage) → finisher-count blurb ("60,000 runners…").
  - The 2026 edition has not been run yet, so no podium is available.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Iterable, List

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Filename substring → clean brand. Lowercase keys; first match wins.
_FILE_BRAND_MAP: list[tuple[str, str]] = [
    ("tcs-newlogo",            "TCS (Tata Consultancy Services)"),
    ("mizuno",                 "Mizuno"),
    ("gemeente-amsterdam",     "Gemeente Amsterdam"),
    ("klm",                    "KLM"),
    ("samsung",                "Samsung"),
    ("all4running",            "All4Running"),
    ("action",                 "Action"),
    ("maurten",                "Maurten"),
    ("runna",                  "Runna"),
    ("trainmore",              "TrainMore"),
    ("telegraaf",              "De Telegraaf"),
    ("freshwater",             "Freshwater"),
    ("chiquita",               "Chiquita"),
    ("topsportamsterdam",      "Topsport Amsterdam"),
    ("buko-infra",             "Buko Infrasupport"),
    ("nh-logo",                "NH Hotels"),
    ("iamsterdam",             "I amsterdam"),
    ("renewi",                 "Renewi"),
    ("foryou",                 "ForYou"),
    ("osstadion",              "Olympic Stadion Amsterdam"),
    ("dixi-logo",              "Dixi"),
    ("fas-logo",               "Finish As One"),
    ("intersettle",            "Intersettle"),
    ("koninklijke-begeer",     "Koninklijke Begeer"),
    ("waternet",               "Waternet"),
    ("hardlopen.nl",           "Hardlopen.nl"),
    ("marathon-photos",        "Marathon-Photos"),
    ("gsc-",                   "GSC"),
    ("gvb-",                   "GVB"),
    ("global-running",         "Global Running"),
    ("kwf-",                   "KWF Kankerbestrijding"),
    ("umc-cca",                "Amsterdam UMC – CCA"),
    ("jsf",                    "Johan Cruyff Foundation"),
    ("world-atletics",         "World Athletics"),
    ("european-atletics",      "European Athletics"),
    ("atletiekunie",           "Atletiekunie"),
    ("aims-",                  "AIMS"),
    ("rai",                    "RAI Amsterdam"),
]

# Section headers on /sponsors. Lowercase keys.
_TITLE_HEADERS = {"titelsponsor"}
_OTHER_HEADERS = {
    "hoofdsponsor", "co-sponsors", "sub-sponsors", "partners",
    "goede doelen", "aangesloten bij",
}
_SKIP_HEADERS = {"sponsormogelijkheden", "de sponsors stellen zich graag aan je voor"}

_LOGO_GENERIC_FILES = {"tam26nieuw-543x543.png", ""}

_FINISHER_RE = re.compile(r"([\d.,]{4,})\s+(?:runners|hardlopers|finishers|deelnemers)", re.I)


@register("tcs-amsterdam-marathon")
class TCSAmsterdamScraper(BaseScraper):
    official_url = "https://www.tcsamsterdammarathon.nl/en/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Le Champion",
            title_sponsor="TCS (Tata Consultancy Services)",
            edition=51,           # 2025 was the 50th edition
            inception_year=1975,
            notes="Race scheduled 2026-10-18; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_homepage_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.tcsamsterdammarathon.nl/sponsors")
        if soup is None:
            return

        # Walk the document in order, tracking which sponsor section we
        # are in based on the most recent <h3> header.
        current = ""
        title_brands: list[str] = []
        other_brands: list[str] = []
        seen: set[str] = set()
        for el in soup.descendants:
            name = getattr(el, "name", None)
            if name == "h3":
                label = el.get_text(" ", strip=True).lower()
                if label in _SKIP_HEADERS:
                    current = ""
                elif label in _TITLE_HEADERS:
                    current = "title"
                elif label in _OTHER_HEADERS:
                    current = "other"
                else:
                    current = ""
                continue
            if name != "img" or not current:
                continue
            base = (el.get("src") or "").rsplit("/", 1)[-1].split("?")[0].lower()
            if not base or base in _LOGO_GENERIC_FILES:
                continue
            brand = self._brand_for(base)
            if not brand or brand in seen:
                continue
            seen.add(brand)
            if current == "title":
                title_brands.append(brand)
            else:
                other_brands.append(brand)

        if title_brands:
            facts.title_sponsor = title_brands[0]
        if other_brands:
            facts.other_sponsors = "\n".join(other_brands)

    def _extract_homepage_stats(self, facts: RaceFacts) -> None:
        # Walk the homepage and the /other-information page (which holds
        # the published "Statistieken" page and links to a
        # statistics PDF) for finisher counts, gender splits, and
        # spectator / volunteer copy.
        for url in (
            self.official_url,
            "https://www.tcsamsterdammarathon.nl/other-information",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)

            m = _FINISHER_RE.search(text)
            if m:
                raw = m.group(1).replace(".", "").replace(",", "")
                try:
                    n = int(raw)
                except ValueError:
                    n = 0
                # Sanity: marathons publish 5-figure participant counts.
                if 5_000 <= n <= 200_000:
                    facts.finishers_total = n

            sm = re.search(r"([\d.,]{3,7})\s*\+?\s+(?:spectators|toeschouwers)", text, re.I)
            if sm:
                try:
                    n = int(sm.group(1).replace(".", "").replace(",", ""))
                    if 1_000 <= n <= 5_000_000:
                        facts.spectators = n
                except ValueError:
                    pass

            vm = re.search(r"([\d.,]{3,6})\s+(?:volunteers|vrijwilligers)", text, re.I)
            if vm:
                try:
                    n = int(vm.group(1).replace(".", "").replace(",", ""))
                    if 50 <= n <= 50_000:
                        facts.volunteers = n
                except ValueError:
                    pass

            wm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+(?:women|vrouwen)", text, re.I)
            if wm:
                try:
                    facts.finishers_women_pct = float(wm.group(1))
                except ValueError:
                    pass
            mm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+(?:men|mannen)", text, re.I)
            if mm:
                try:
                    facts.finishers_men_pct = float(mm.group(1))
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    @staticmethod
    def _brand_for(filename: str) -> str:
        for needle, brand in _FILE_BRAND_MAP:
            if needle in filename:
                return brand
        return ""

    @staticmethod
    def _join(parts: Iterable[str]) -> str:
        return "\n".join(p for p in parts if p)
