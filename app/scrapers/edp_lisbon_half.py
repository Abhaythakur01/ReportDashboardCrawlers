"""EDP Lisbon Half Marathon — https://www.maratonaclubedeportugal.com/

The EDP Meia Maratona de Lisboa runs in March every year. The 2026
edition was the 34th. The race has two starts — a popular field that
crosses the 25 de Abril Bridge from Almada plus an elite field
starting in Algés. Together they form one of the largest half
marathons in Iberia.

Scope:
  - Stable race facts (organizer, title sponsor, edition) are pinned.
  - The Maratona Clube de Portugal blog carries pre-race promotion
    articles that cite the popular-field cap ("esgotada desde outubro
    de 2024, com mais de 20 mil inscritos"). We pull that as the
    finishers_total approximation when no post-race recap exists.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_BLOG_BASE = "https://www.maratonaclubedeportugal.com/blog/"

# Blog post slugs that the site uses for the half-marathon promotional
# article (Ruth Chepngetich coverage). Stable enough to hardcode as a
# direct fetch target — saves a brittle list-page scrape.
_HALF_PROMO_SLUGS = [
    "a-primeira-mulher-a-correr-a-maratona-em-menos-de-210-horas-vem-a-lisboa-bater-o-recorde-do-mundo-da-meia-maratona",
]

_HIGHLIGHT_KEYWORDS = (
    "meia maratona", "edp", "lisboa", "chepngetich", "maratona", "elite",
)


@register("edp-lisbon-half-marathon")
class EDPLisbonHalfScraper(BaseScraper):
    official_url = "https://www.maratonaclubedeportugal.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Maratona Clube de Portugal",
            title_sponsor="EDP",
            inception_year=1991,  # First EDP-titled half ran in 1991; 2026 = 34th edition
            edition=34,
        )

        # Pull the promo article directly — it has the registration cap.
        for slug in _HALF_PROMO_SLUGS:
            url = f"https://www.maratonaclubedeportugal.com/{slug}/"
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)
            self._extract_promo_meta(text, facts)
            break

        # Highlights from the blog index.
        self._extract_highlights(facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_promo_meta(self, text: str, facts: RaceFacts) -> None:
        # "esgotada desde outubro de 2024, com mais de 20 mil inscritos"
        # The popular field caps at 20,000 — that's the registered field
        # for 2026. Used as a finishers_total approximation.
        m = re.search(r"mais\s+de\s+(\d{1,3})\s*mil\s+inscritos", text, re.I)
        if m and facts.finishers_total is None:
            try:
                facts.finishers_total = int(m.group(1)) * 1000
            except ValueError:
                pass

        # Edition mention: "34.ª edição"
        m_ed = re.search(r"(\d{1,3})[\.\º°ª]?\s*edi[çc][ãa]o", text, re.I)
        if m_ed:
            try:
                ed = int(m_ed.group(1))
                if 20 <= ed <= 60:
                    facts.edition = ed
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(_BLOG_BASE)
        if soup is None:
            return
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 18 or len(text) > 220:
                continue
            full = href if href.startswith("http") else "https://maratonaclubedeportugal.com" + href
            if "www.maratonaclubedeportugal.com" not in full or full in seen:
                continue
            tail = full.rstrip("/").rsplit("/", 1)[-1]
            if not tail or tail in {"blog", "noticias", "page"}:
                continue
            if any(t in full for t in ("/category/", "/tag/", "/page/", "/author/")):
                continue
            if len(tail) < 16:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
