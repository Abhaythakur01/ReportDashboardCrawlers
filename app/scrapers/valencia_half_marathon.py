"""Medio Maraton Valencia Trinidad Alfonso Zurich — https://www.valenciaciudaddelrunning.com/

The 2026 Valencia Half Marathon is the 36th edition (inaugural 1991),
scheduled for 2026-10-25. World Athletics Gold Label road race. Shares
the host with the full marathon; everything sits under /medio/.

Pulls:
  - /medio/patrocinadores-medio-maraton/  -> sponsor roster
  - /medio/noticias-medio-maraton/        -> top news titles + URLs
  - /medio/presentacion-medio-maraton/    -> edition fallback

Title sponsor is "Trinidad Alfonso Zurich" branding (Fundacion Trinidad
Alfonso main collaborator + Zurich title insurer). Note that the
mediomaratonvalencia.com vanity domain 301-redirects to /medio/medio-maraton/
on the main host, so we keep the official_url set to that main host —
this lets the scraper share infrastructure with the full marathon.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_LOGO_TOKEN_MAP: list[tuple[str, str]] = [
    ("zurich", "Zurich"),
    ("trinidad alfonso", "Fundacion Trinidad Alfonso"),
    ("fundacion trinidad", "Fundacion Trinidad Alfonso"),
    ("ajuntament", "Ajuntament de Valencia"),
    ("caixabank", "CaixaBank"),
    ("coca-cola", "Coca-Cola"),
    ("coca cola", "Coca-Cola"),
    ("cocacola", "Coca-Cola"),
    ("msc", "MSC"),
    ("feria valencia", "Feria Valencia"),
    ("central lechera", "Central Lechera Asturiana"),
    ("carnicas serrano", "Carnicas Serrano"),
    ("enervit", "Enervit"),
    ("vithas", "Vithas"),
    ("hyundai", "Hyundai"),
    ("patatas melendez", "Patatas Melendez"),
    ("coros", "COROS"),
    ("oakberry", "OakBerry"),
    ("platano", "Platano de Canarias"),
    ("isaval", "Isaval"),
    ("persimon", "Persimon Bouquet"),
    ("aquarius", "Aquarius"),
    ("bertolin", "Grupo Bertolin"),
    ("importaco", "Importaco"),
    ("velarte", "Velarte"),
    ("ceralto", "Ceralto"),
    ("teika", "Teika"),
    ("physiorelax", "Physiorelax"),
    ("colacao", "ColaCao"),
    ("rnb", "RNB Cosmeticos"),
    ("yamaha", "Yamaha"),
    ("ecoembes", "Ecoembes"),
    ("renfe", "Renfe"),
    ("correcaminos", "S.D. Correcaminos"),
]

_NEWS_KEYWORDS = (
    "medio", "maraton", "valencia", "atletismo", "zurich",
    "correcaminos", "fundacion", "trinidad", "edicion", "elite",
)

_EDITION_RE = re.compile(r"\b(\d{1,3})[ªa\s\.\-]*\s*edici[oó]n", re.I)


@register("medio-marathon-valencia-trinidad-alfonso-zurich")
class ValenciaHalfMarathonScraper(BaseScraper):
    official_url = "https://www.valenciaciudaddelrunning.com/"

    def __init__(self, official_url: str | None = None) -> None:
        # The race-list datasource lists this race under its vanity domain
        # (mediomaratonvalencia.com), but that domain 301-redirects every
        # request to the parent host. Anchor the scraper to the parent host
        # regardless of what the caller passes so BaseScraper's host check
        # still permits the real source URLs.
        super().__init__(official_url="https://www.valenciaciudaddelrunning.com/")

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="S.D. Correcaminos; Ajuntament de Valencia",
            title_sponsor="Trinidad Alfonso Zurich",
            edition=36,            # 1st edition 1991 -> 2026 = 36th
            inception_year=1991,
            notes="Race scheduled 2026-10-25; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_edition_from_presentation(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(
            "https://www.valenciaciudaddelrunning.com/medio/patrocinadores-medio-maraton/"
        )
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
        title_tokens = {
            "zurich", "fundacion trinidad alfonso",
            "ajuntament de valencia", "s.d. correcaminos",
        }
        others = [b for b in ordered if b.lower() not in title_tokens]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(
            "https://www.valenciaciudaddelrunning.com/medio/noticias-medio-maraton/"
        )
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
            # (https://host/<slug>/). Section pages live under /medio/ or
            # /maraton/. Filter to the top-level shape.
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
    def _extract_edition_from_presentation(self, facts: RaceFacts) -> None:
        soup = self.get(
            "https://www.valenciaciudaddelrunning.com/medio/presentacion-medio-maraton/"
        )
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = _EDITION_RE.search(text)
        if m:
            try:
                ed = int(m.group(1))
                if 20 <= ed <= 60:
                    facts.edition = ed
            except ValueError:
                pass
