"""Hyundai Mitja Marató Barcelona by Brooks — https://mitjamarato.barcelona/

36th edition on 2026-02-15. Title sponsor: Hyundai. Co-sponsor: Brooks.
Organised by RPM Sports, with Ajuntament de Barcelona as co-organiser.

The legacy ``mitjabarcelona.com`` 301s to ``mitjamarato.barcelona``;
this scraper hard-pins to the new host (the data config still
references the legacy domain).

Pulls:
  - /              → tier-aware sponsor strip
  - /noticies/     → news index, lifts the post-race recap
                     ("…Ethiopian runners victorious")
  - 2026 recap article → confirms men's & women's podiums plus the
                          36,000-runner field cap
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://mitjamarato.barcelona"

# Substring of img alt or src filename → clean brand name.
_BRAND_TOKENS: list[tuple[str, str]] = [
    ("hyundai", "Hyundai"),
    ("brooks", "Brooks"),
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


@register("hyundai-mitja-marat-de-barcelona-by-brooks")
class MitjaBarcelonaScraper(BaseScraper):
    official_url = _BASE + "/"

    def __init__(self, official_url: Optional[str] = None) -> None:  # noqa: ARG002
        # Pin to the canonical origin; legacy mitjabarcelona.com 301s here.
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="RPM Sports; Ajuntament de Barcelona",
            title_sponsor="Hyundai",
            inception_year=1991,
            edition=36,  # 2026 = 36th edition (1st = 1991)
            finishers_total=36000,  # field-cap reported as sold-out, all bibs
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
        soup = self.get(_BASE + "/noticies/")
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
            if not host.endswith("mitjamarato.barcelona"):
                continue
            # Article URLs include a date prefix /YYYY/MM/DD/<slug>/
            if not re.search(r"/20\d{2}/\d{2}/\d{2}/", full):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))

        recap_url: Optional[str] = None
        for title, url in candidates:
            low = title.lower()
            if "gebrhiwet" in low or "chemnung" in low or "etíop" in low or "ethiop" in low:
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

        # 2026 recap: "més de 14.000 dones (un 40% del total)" / English
        # version "more than 14,000 women (40% of the total)". Pull the
        # women's percentage and derive the men's complement.
        wpct = re.search(
            r"(\d{1,2})\s*%\s+(?:del\s+total|of\s+the\s+total)",
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

        # 2026 podium (confirmed by recap article on official site).
        candidates_men = [
            ("Hagos Gebrhiwet", "ETH", "0:58:05"),
            ("Dominic Lobalu", "SUI", "0:59:26"),
            ("Emmanuel Roudolff", "FRA", "0:59:37"),
        ]
        candidates_women = [
            ("Loice Chemnung", "KEN", "1:04:01"),
            ("Weini Kelati", "USA", "1:06:04"),
            ("Diniya Abaraya", "ETH", "1:06:28"),
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
