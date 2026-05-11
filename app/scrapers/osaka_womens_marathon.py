"""Osaka International Women's Marathon — official_url path /women/ on
https://www.osaka-marathon.com/

The Osaka International Women's Marathon (大阪国際女子マラソン) is one
of the world's longest-running elite women's marathons. Inaugural
edition: 1982. Held annually on the last Sunday of January. 2026 is
the 45th edition.

Pulls (best-effort; the /women/ path on osaka-marathon.com may 404 in
which case the scraper falls back to hardcoded baseline facts):
  - /women/                  -> homepage / sponsor logos / news anchors
  - /women/sponsor/          -> sponsor list
  - /women/news/             -> recent news (top 5 highlights)

Per the BaseScraper rule, this scraper only fetches from the same
osaka-marathon.com origin (the host check matches www.osaka-marathon.com
exactly — the same host the men's race uses, so any /women/* path is
allowed).

Organizers: Sankei Shimbun, Kansai Telecasting Corp., Osaka Athletics
Association, JAAF — title sponsor historically has been Sankei
Shimbun (the founding promoter); recent editions surface Daihatsu
Diesel and other partners.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_SPONSOR_TOKEN_MAP: list[tuple[str, str]] = [
    ("sankei", "Sankei Shimbun"),
    ("ktv", "Kansai Telecasting Corporation"),
    ("kansai-tv", "Kansai Telecasting Corporation"),
    ("daihatsu", "Daihatsu"),
    ("seiko", "Seiko"),
    ("mizuno", "Mizuno"),
    ("asics", "ASICS"),
    ("toyota", "Toyota"),
    ("japan post", "Japan Post"),
    ("jp-bank", "Japan Post Bank"),
    ("morinaga", "Morinaga"),
    ("ajinomoto", "Ajinomoto"),
    ("pocari", "Pocari Sweat"),
    ("otsuka", "Otsuka Pharmaceutical"),
]

_NEWS_KEYWORDS_JA = ("女子", "マラソン", "大阪", "ランナー", "結果")
_NEWS_KEYWORDS_EN = ("women", "marathon", "osaka", "result", "runner")


@register("osaka-women-s-marathon")
class OsakaWomensMarathonScraper(BaseScraper):
    official_url = "https://www.osaka-marathon.com/women/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Sankei Shimbun, Kansai Telecasting Corporation, "
                "Osaka Athletics Association, Japan Association of "
                "Athletics Federations (JAAF)"
            ),
            title_sponsor="Sankei Shimbun",
            inception_year=1982,
            edition=45,  # 1982 = 1st, held annually; 2026 = 45th.
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_edition(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        # Try the dedicated sponsor page first; fall back to homepage.
        for url in (
            "https://www.osaka-marathon.com/women/sponsor/",
            "https://www.osaka-marathon.com/women/info/sponsor/",
            "https://www.osaka-marathon.com/women/",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            seen: set[str] = set()
            ordered: list[str] = []
            for img in soup.find_all("img"):
                alt = (img.get("alt") or "").lower()
                src = (img.get("src") or "").lower()
                haystack = alt + " " + src.rsplit("/", 1)[-1]
                for needle, brand in _SPONSOR_TOKEN_MAP:
                    if needle in haystack and brand not in seen:
                        seen.add(brand)
                        ordered.append(brand)
                        break
            if ordered:
                others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
                if others:
                    facts.other_sponsors = "\n".join(others)
                return

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        for url in (
            "https://www.osaka-marathon.com/women/news/",
            "https://www.osaka-marathon.com/women/",
        ):
            soup = self.get(url)
            if soup is None:
                continue

            seen: set[str] = set()
            candidates: List[tuple[str, str]] = []
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 6:
                    continue
                full = href if href.startswith("http") else "https://www.osaka-marathon.com" + href
                if "osaka-marathon.com" not in full:
                    continue
                if "/women/" not in full:
                    continue
                if not re.search(r"/(news|press|topics)/", full):
                    continue
                if full in seen:
                    continue
                tlow = text.lower()
                if not (any(k in text for k in _NEWS_KEYWORDS_JA) or any(k in tlow for k in _NEWS_KEYWORDS_EN)):
                    continue
                seen.add(full)
                candidates.append((text[:140], full))
                if len(candidates) >= 5:
                    break
            if candidates:
                for title, u in candidates:
                    facts.highlights.append((title, u))
                return

    # ------------------------------------------------------------------
    def _extract_edition(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.osaka-marathon.com/women/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"第\s*(\d{1,3})\s*回\s*大阪国際女子マラソン", text)
        if m:
            try:
                facts.edition = int(m.group(1))
                return
            except ValueError:
                pass
        m = re.search(
            r"\b(\d{1,3})(?:st|nd|rd|th)\s+Osaka(?:\s+International)?\s+Women",
            text,
            re.I,
        )
        if m:
            try:
                facts.edition = int(m.group(1))
            except ValueError:
                pass
