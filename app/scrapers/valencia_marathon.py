"""Maraton Valencia Trinidad Alfonso Zurich — https://www.valenciaciudaddelrunning.com/

The 2026 Valencia Marathon is the 46th edition (inaugural 1981), scheduled
for 2026-12-06. World Athletics Platinum Label road race. The site is in
Spanish; sponsor and news pages live under /maraton/.

Pulls:
  - /maraton/patrocinadores/    -> sponsor roster (img alt + brand whitelist)
  - /maraton/noticias-maraton/  -> top recent news titles + URLs
  - /maraton/presentacion/      -> organizer line + edition fallback

Title sponsor is officially "Trinidad Alfonso Zurich" (Fundacion Trinidad
Alfonso is the main collaborator, Zurich is the title insurer). The site
itself credits Zurich as the headline sponsor; we keep both names in
title_sponsor for the report's branding line.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Sponsor whitelist — substring of either img alt text or src filename ->
# clean brand name. Keys lowercase. Order is roughly tier (title first).
_LOGO_TOKEN_MAP: list[tuple[str, str]] = [
    ("zurich", "Zurich"),
    ("trinidad alfonso", "Fundacion Trinidad Alfonso"),
    ("fundacion trinidad", "Fundacion Trinidad Alfonso"),
    ("ajuntament", "Ajuntament de Valencia"),
    ("new balance", "New Balance"),
    ("newbalance", "New Balance"),
    ("caixabank", "CaixaBank"),
    ("powerade", "Powerade"),
    ("movistar", "Movistar"),
    ("msc", "MSC"),
    ("feria valencia", "Feria Valencia"),
    ("central lechera", "Central Lechera Asturiana"),
    ("carnicas serrano", "Carnicas Serrano"),
    ("enervit", "Enervit"),
    ("vithas", "Vithas"),
    ("hyundai", "Hyundai"),
    ("patatas melendez", "Patatas Melendez"),
    ("coros", "COROS"),
    ("midea", "Midea"),
    ("colacao", "ColaCao"),
    ("isaval", "Isaval"),
    ("persimon", "Persimon Bouquet"),
    ("fuze tea", "Fuze Tea"),
    ("yamaha", "Yamaha"),
    ("bertolin", "Grupo Bertolin"),
    ("importaco", "Importaco"),
    ("nocilla", "Nocilla"),
    ("brillante", "Brillante"),
    ("teika", "Teika"),
    ("platano", "Platano de Canarias"),
    ("ecoembes", "Ecoembes"),
    ("renfe", "Renfe"),
    ("correcaminos", "S.D. Correcaminos"),
]

_NEWS_KEYWORDS = (
    "maraton", "valencia", "atletismo", "zurich", "correcaminos",
    "fundacion", "trinidad", "edicion", "elite", "record",
)

_EDITION_RE = re.compile(r"\b(\d{1,3})[ªa\s\.\-]*\s*edici[oó]n", re.I)


@register("marat-n-valencia-trinidad-alfonso-zurich")
class ValenciaMarathonScraper(BaseScraper):
    official_url = "https://www.valenciaciudaddelrunning.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="S.D. Correcaminos; Ajuntament de Valencia",
            title_sponsor="Trinidad Alfonso Zurich",
            edition=46,            # 1st edition 1981 -> 2026 = 46th
            inception_year=1981,
            notes="Race scheduled 2026-12-06; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_edition_from_presentation(facts)
        self._extract_anniversary_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.valenciaciudaddelrunning.com/maraton/patrocinadores/")
        if soup is None:
            return
        seen: set[str] = set()
        ordered: List[str] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").lower()
            src = (img.get("src") or "").lower()
            haystack = alt + " " + src.rsplit("/", 1)[-1]
            for needle, brand in _LOGO_TOKEN_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        # Drop the title-sponsor brands and the organizers so they don't
        # double-count (organizers already on facts.organizers).
        title_tokens = {
            "zurich", "fundacion trinidad alfonso",
            "ajuntament de valencia", "s.d. correcaminos",
        }
        others = [b for b in ordered if b.lower() not in title_tokens]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.valenciaciudaddelrunning.com/maraton/noticias-maraton/")
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
                "https://www.valenciaciudaddelrunning.com" + href
            )
            if "valenciaciudaddelrunning.com" not in full:
                continue
            if full in seen:
                continue
            # News articles on this site live at top-level slugs
            # (https://host/<slug>/). Section pages live under /maraton/ or
            # /medio/. Filter to the top-level shape.
            path = full.split("valenciaciudaddelrunning.com", 1)[-1].strip("/")
            if not path or "/" in path or len(path) < 18:
                continue
            if "#" in path:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _NEWS_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:200], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _extract_anniversary_stats(self, facts: RaceFacts) -> None:
        """The /maraton/40-aniversario/ page is a yearly recap with
        finisher counts ("more than 21,200 finishers... 4,000 women")
        and the inaugural 1981 figure. The /presentacion/ page
        occasionally surfaces volunteer / spectator numbers."""
        soup = self.get("https://www.valenciaciudaddelrunning.com/maraton/40-aniversario/")
        if soup is not None:
            text = soup.get_text(" ", strip=True)
            # Pull the highest finisher figure published — the page is
            # a chronological build-up of records ("21,200 finishers").
            best_total: int = 0
            best_women: int = 0
            for m in re.finditer(
                r"(?:more\s+than|over|m[áa]s\s+de)\s+([\d.,]{4,7})\s+(?:runners|finishers|corredores|atletas)",
                text,
                re.I,
            ):
                try:
                    n = int(m.group(1).replace(".", "").replace(",", ""))
                except ValueError:
                    continue
                if 5_000 <= n <= 100_000 and n > best_total:
                    best_total = n
            for m in re.finditer(
                r"([\d.,]{3,5})\s+(?:women|mujeres)",
                text,
                re.I,
            ):
                try:
                    n = int(m.group(1).replace(".", "").replace(",", ""))
                except ValueError:
                    continue
                if 500 <= n <= 30_000 and n > best_women:
                    best_women = n
            if best_total:
                facts.finishers_total = best_total
                if best_women:
                    pct = round(100.0 * best_women / best_total, 1)
                    if 1 <= pct <= 70:
                        facts.finishers_women_pct = pct
                        facts.finishers_men_pct = round(100.0 - pct, 1)

        # Prize money — Valencia's official site publishes the public
        # purse for Spanish nationals and record bonuses on the 2026
        # regulations page. We sum the published Spanish-nationals
        # ladder (top 5, both genders) as the documented USD-equivalent
        # purse; record bonuses are conditional and not booked.
        soup = self.get("https://www.valenciaciudaddelrunning.com/maraton/reglamento-42k-2026/")
        if soup is not None:
            text = soup.get_text(" ", strip=True)
            # Try to capture an aggregate "premios en met[áa]lico ... X"
            m = re.search(
                r"(?:premios|bolsa|fondo)\s+(?:en\s+)?met[áa]lico\s*[:\-]?\s*([\d.,]{3,9})\s*(?:€|EUR|euros)?",
                text,
                re.I,
            )
            if m:
                try:
                    n = int(m.group(1).replace(".", "").replace(",", ""))
                    if 50_000 <= n <= 5_000_000:
                        # Spanish nationals ladder is published in EUR;
                        # convert to USD at a stable 1.10 EUR/USD rate.
                        facts.prize_money_usd = int(round(n * 1.10))
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    def _extract_edition_from_presentation(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.valenciaciudaddelrunning.com/maraton/presentacion/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = _EDITION_RE.search(text)
        if m:
            try:
                ed = int(m.group(1))
                # Only override the hardcoded value if site stated edition is
                # a sane forward-of-2025 number.
                if 30 <= ed <= 80:
                    facts.edition = ed
            except ValueError:
                pass
