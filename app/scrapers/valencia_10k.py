"""10K Valencia Ibercaja by Kiprun — https://www.10kvalencia.com/

Held annually in Valencia, Spain since 2014; the January 2026 edition
was the 12th. Title sponsor: Ibercaja (the bank), with Decathlon's
Kiprun running brand co-titling the race. Organised by the Club
Atletismo 10K Valencia Ibercaja, sister club to the Trinidad Alfonso
foundation that runs the city's marathon and half.

The official site is largely a static HTML site with sponsor img logos
and a Spanish-language news index — both scrape cleanly without JS.

The post-race recap article ("records-nacionales") quotes the field:
"14.134 corredores llegados a meta" (14,134 finishers at the 10K),
plus "229 hombres y cuatro mujeres" sub-30 — i.e. the elite slice is
overwhelmingly male, but the recap doesn't break down the full field.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_FILENAME_BRAND_MAP: list[tuple[str, str]] = [
    ("ibercaja",      "Ibercaja"),
    ("kiprun",        "Kiprun"),
    ("quiron",        "Quirón Salud"),
    ("coros",         "Coros"),
    ("coca-cola",     "Coca-Cola"),
    ("cocacola",      "Coca-Cola"),
    ("226ers",        "226ERS"),
    ("hyundai",       "Hyundai Autiber Motor"),
    ("autiber",       "Hyundai Autiber Motor"),
    ("divina",        "Divina Seguros"),
    ("decathlon",     "Decathlon"),
    ("trinidad",      "Fundación Trinidad Alfonso"),
]

_HIGHLIGHT_KEYWORDS = (
    "10k", "valencia", "ibercaja", "kiprun", "carrera", "récord",
    "record", "ganador", "campeón", "champion", "winner",
)


@register("10k-valencia-ibercaja-by-kiprun")
class Valencia10kScraper(BaseScraper):
    # Pin to the bare-host canonical origin. The site's news permalinks
    # use the bare host (``10kvalencia.com``) while the ``www.`` variant
    # 301s — fixing on the bare host means in-origin article URLs pass
    # the BaseScraper's host check.
    official_url = "https://10kvalencia.com/"

    def __init__(self, official_url: Optional[str] = None) -> None:  # noqa: ARG002
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Club Atletismo 10K Valencia Ibercaja",
            title_sponsor="Ibercaja / Kiprun",
            edition=12,           # 1st edition 2014; 2026 = 12th (held Jan 2026)
            inception_year=2014,
        )
        self._extract_sponsors(facts)
        recap_url = self._extract_highlights(facts)
        if recap_url:
            self._extract_recap_stats(recap_url, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_recap_stats(self, url: str, facts: RaceFacts) -> None:
        """Pull the 10K finisher count from the post-race recap article.

        The 2026 recap ("records-nacionales") writes the number out as
        "14.134 corredores llegados a meta" — Spanish thousands use a
        period as the grouping separator.
        """
        soup = self.get(url)
        if soup is None:
            return
        body = soup.find("article") or soup.find("main") or soup
        text = body.get_text(" ", strip=True)
        # "14.134 corredores llegados a meta" / "...llegaron a meta"
        m = re.search(
            r"(\d{1,2}\.\d{3})\s+corredores\s+(?:llegados?|llegaron)\s+a\s+meta",
            text,
            re.I,
        )
        if m and facts.finishers_total is None:
            try:
                facts.finishers_total = int(m.group(1).replace(".", ""))
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            alt = (img.get("alt") or "").lower()
            haystack = src.rsplit("/", 1)[-1] + " " + alt
            for needle, brand in _FILENAME_BRAND_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [b for b in ordered if b not in {"Ibercaja", "Kiprun"}]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        """Surface news highlights and identify the post-race recap URL.

        The 2026 recap ("records-nacionales") drops national records and
        is the article that quotes the finisher count we want. We lift
        it to position 1 when present.
        """
        soup = self.get(self.official_url)
        if soup is None:
            return None
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 25 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "10kvalencia.com" not in full:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in {"noticias", "blog", ""}:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:160], full))

        recap_url: Optional[str] = None
        for title, url in candidates:
            tl = title.lower()
            if "récord" in tl or "record" in tl or "records-nacionales" in url.lower():
                recap_url = url
                break
        if recap_url:
            candidates.sort(key=lambda c: 0 if c[1] == recap_url else 1)
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
        return recap_url
