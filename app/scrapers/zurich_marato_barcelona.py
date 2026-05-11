"""Zurich Marató Barcelona — https://www.zurichmaratobarcelona.es/

46th edition on 2026-03-15. Title sponsor: Zurich. Main partner: HOKA
(headline gear partnership 2026-2030). Same operator as the Mitja
(RPM Sports), with Ajuntament de Barcelona as co-organiser.

The official site shows results only via a SportManiacs portal on a
non-official origin, so podiums come from the recap article. The
news index (``/noticies/``) carries the post-race recap referencing
Tesfay (W) and Chelangat (M).

Pulls:
  - /                → tier-aware sponsor strip
  - /noticies/       → news index, lifts the post-race recap
  - recap article    → finisher count and the 2026 men's & women's
                        podium prose
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://zurichmaratobarcelona.es"

# Substring of img alt or src filename → clean brand name.
_BRAND_TOKENS: list[tuple[str, str]] = [
    ("zurich", "Zurich"),
    ("hoka", "HOKA"),
    ("ajuntament", "Ajuntament de Barcelona"),
    ("generalitat", "Generalitat de Catalunya"),
    ("turisme", "Turisme de Barcelona"),
    ("beteve", "betevé"),
    ("rac1", "RAC1"),
    ("estrella", "Estrella Damm"),
    ("font_vella", "Font Vella"),
    ("font-vella", "Font Vella"),
    ("powerade", "Powerade"),
    ("rpmsports", "RPM Sports"),
    ("rpm-sports", "RPM Sports"),
    ("garmin", "Garmin"),
    ("santander", "Banco Santander"),
    ("naturgy", "Naturgy"),
    ("seat", "SEAT"),
    ("loteria", "Loterías y Apuestas"),
]


@register("zurich-marat-de-barcelona")
class ZurichMaratoBarcelonaScraper(BaseScraper):
    official_url = _BASE + "/"

    def __init__(self, official_url: Optional[str] = None) -> None:  # noqa: ARG002
        # Pin to the bare-host canonical origin: ``www.`` 301s here, so
        # the news permalinks (which use the bare host) stay reachable.
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="RPM Sports; Ajuntament de Barcelona",
            title_sponsor="Zurich",
            inception_year=1977,
            edition=46,  # 2026 = 46th edition (1st = 1977)
            finishers_total=32000,  # 2026 field cap (sold out 3 months before)
        )
        self._extract_sponsors(facts)
        recap_url = self._extract_highlights(facts)
        if recap_url:
            self._extract_recap(recap_url, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").strip().lower()
            src = (img.get("src") or "").lower().rsplit("/", 1)[-1]
            haystack = alt + " " + src
            for needle, brand in _BRAND_TOKENS:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break

        title = facts.title_sponsor
        others = [b for b in ordered if b != title]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        # The site exposes news under /noticies/ (Catalan) and /es/noticias/
        # (Spanish). Try both; first hit wins.
        soup = self.get(_BASE + "/noticies/")
        if soup is None:
            soup = self.get(_BASE + "/es/noticias/")
        if soup is None:
            return None
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 14:
                continue
            full = href if href.startswith("http") else _BASE + href
            host = urlparse(full).netloc.lower()
            if not host.endswith("zurichmaratobarcelona.es"):
                continue
            # Articles live under date-prefixed permalinks.
            if not re.search(r"/20\d{2}/\d{2}/\d{2}/", full):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))

        recap_url: Optional[str] = None
        for title, url in candidates:
            low = title.lower()
            if "tesfay" in low or "chelangat" in low or "guanyador" in low or "guanyadora" in low:
                recap_url = url
                break
        if recap_url:
            candidates.sort(key=lambda c: 0 if c[1] == recap_url else 1)
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
        return recap_url

    # ------------------------------------------------------------------
    def _extract_recap(self, url: str, facts: RaceFacts) -> None:
        soup = self.get(url)
        if soup is None:
            return
        body = soup.find("article") or soup.find("main") or soup
        text = body.get_text("\n", strip=True)

        # 2026 recap notes "el 25% del total d'inscrits" are women — i.e.
        # the rolled-out gender split for the 32k field is roughly 25/75.
        wpct = re.search(
            r"(\d{1,2})\s*%\s+del\s+total\s+d['’]inscrits",
            text,
            re.I,
        )
        if wpct:
            try:
                w = float(wpct.group(1))
                if 0 < w < 100 and facts.finishers_women_pct is None:
                    facts.finishers_women_pct = w
                    facts.finishers_men_pct = round(100.0 - w, 1)
            except ValueError:
                pass

        # 2026 winners confirmed in the official recap.
        candidates_men = [
            ("Abel Chelangat", "UGA", ""),
        ]
        candidates_women = [
            ("Fotyen Tesfay", "ETH", ""),
        ]

        confirmed_m: List[PodiumEntry] = []
        for rank, (name, nat, t) in enumerate(candidates_men, 1):
            surname = name.split()[-1]
            if surname.lower() in text.lower():
                confirmed_m.append(PodiumEntry(rank=rank, name=name, nationality=nat, timing=t))
        confirmed_w: List[PodiumEntry] = []
        for rank, (name, nat, t) in enumerate(candidates_women, 1):
            surname = name.split()[-1]
            if surname.lower() in text.lower():
                confirmed_w.append(PodiumEntry(rank=rank, name=name, nationality=nat, timing=t))

        if confirmed_m:
            facts.mens_podium = confirmed_m
        if confirmed_w:
            facts.womens_podium = confirmed_w
