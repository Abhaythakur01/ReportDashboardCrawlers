"""Osaka Marathon — https://www.osaka-marathon.com/

The mass-participation Osaka Marathon. Inaugural 2011, held annually
(except 2021 cancellation due to COVID); 2026 is the 14th edition.
Main sponsor: Osaka Metro. Co-organizer: Yomiuri Shimbun.

Pulls:
  - /2026/info/sponsor/   -> sponsor list
  - /2026/news/           -> latest news (top 5 highlights)
  - /2026/expo/outline/   -> race outline / edition (regex fallback)

Note: the women's race (Osaka International Women's Marathon) lives at
/women/ on the same host but uses an entirely different organizing
body and is handled by ``osaka_womens_marathon.py``.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Outbound host (lowercase) -> (clean brand, tier).
# Tier: 0 = main, 1 = official.
_SPONSOR_HOST_MAP: dict[str, tuple[str, int]] = {
    "subway.osakametro.co.jp": ("Osaka Metro", 0),
    "www.osakametro.co.jp": ("Osaka Metro", 0),
    "www.optage.co.jp": ("Optage", 1),
    "optage.co.jp": ("Optage", 1),
    "www.mizuno.com": ("Mizuno", 1),
    "www.daiwahouse.co.jp": ("Daiwa House", 1),
    "www.bk.mufg.jp": ("MUFG Bank", 1),
    "www.jtb.co.jp": ("JTB", 1),
    "www.sei.co.jp": ("Sumitomo Electric Industries", 1),
    "www.marukome.co.jp": ("Marukome", 1),
    "www.cocacola.co.jp": ("Coca-Cola Japan", 1),
    "www.ccbji.co.jp": ("Coca-Cola Japan", 1),
    "www.seiko.co.jp": ("Seiko", 1),
    "www.kansai-u.ac.jp": ("Kansai University", 1),
    "www.alpen-group.jp": ("Alpen", 1),
    "www.duskin.co.jp": ("Duskin", 1),
    "www.iwatani.co.jp": ("Iwatani", 1),
    "www.kubota.co.jp": ("Kubota", 1),
    "www.maruichikokan.co.jp": ("Maruichi Steel Tube", 1),
    "www.jal.co.jp": ("Japan Airlines", 1),
    "www.nissan-osaka.co.jp": ("Nissan Osaka", 1),
    "www.ajinomoto.co.jp": ("Ajinomoto", 1),
    "www.asahibeer.co.jp": ("Asahi Beer", 1),
    "www.yomiuri.co.jp": ("Yomiuri Shimbun", 1),
}

_NEWS_KEYWORDS_JA = (
    "マラソン", "大阪", "チャリティ", "ボランティ", "ランナー",
)
_NEWS_KEYWORDS_EN = (
    "marathon", "osaka", "charity", "runner", "result",
)


@register("osaka-marathon")
class OsakaMarathonScraper(BaseScraper):
    official_url = "https://www.osaka-marathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Osaka Marathon Organizing Committee (Osaka Prefecture, "
                "Osaka City, Osaka Track and Field Association, JAAF, "
                "Yomiuri Shimbun)"
            ),
            title_sponsor="Osaka Metro",
            inception_year=2011,
            edition=14,  # 2011 = 1st; 2021 cancelled; 2026 = 14th.
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_edition(facts)
        self._extract_outline_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.osaka-marathon.com/2026/info/sponsor/")
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[tuple[str, int]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            host = urlparse(href).netloc.lower()
            entry = _SPONSOR_HOST_MAP.get(host)
            if entry is None:
                continue
            name, tier = entry
            if name in seen:
                continue
            seen.add(name)
            ordered.append((name, tier))

        if not ordered:
            return

        ordered.sort(key=lambda x: x[1])
        title_brands = [n for (n, t) in ordered if t == 0]
        if title_brands:
            facts.title_sponsor = title_brands[0]
        others = [n for (n, t) in ordered if t != 0]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.osaka-marathon.com/2026/news/")
        if soup is None:
            return

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
            # We want individual news articles: /2026/news/<id>/
            if not re.search(r"/news/\d+/?$", full):
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
        for title, url in candidates:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _extract_outline_stats(self, facts: RaceFacts) -> None:
        """The /2026/expo/outline/ page lists the documented runner
        capacity ("34,000 runners") plus EXPO attendance figures,
        which we reuse as a finisher_total upper bound. Volunteer
        counts occasionally surface as ボランティア (volunteer) lines
        on /2026/info/volunteer/ if/when that path is published."""
        for url in (
            "https://www.osaka-marathon.com/2026/expo/outline/",
            "https://www.osaka-marathon.com/2026/info/volunteer/",
            "https://www.osaka-marathon.com/2026/charity/",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)

            # Marathon participant capacity — use the published 34,000
            # ランナー / runners figure when the page surfaces it. The
            # 2026 outline page reads "参加ランナー34,000人" inline.
            for pat in (
                r"ランナー\s*[:：]?\s*(?:約)?\s*([\d,]{4,6})\s*人",
                r"ランナー\s*[:：]?\s*(?:約)?\s*([\d,]{4,6})",
                r"([\d,]{4,6})\s*(?:名|人)\s*(?:のランナー|の参加者)",
                r"([\d,]{4,6})\s+(?:runners|participants|finishers)",
                r"参加者数\s*[:：]?\s*([\d,]{4,6})",
            ):
                m = re.search(pat, text, re.I)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                    except ValueError:
                        continue
                    if 5_000 <= n <= 100_000 and not facts.finishers_total:
                        facts.finishers_total = n
                        break

            # Volunteer count: ボランティア X名 / 約X人
            vm = re.search(r"ボランティア\s*[:：]?\s*(?:約)?\s*([\d,]{3,6})\s*[名人]", text)
            if vm:
                try:
                    n = int(vm.group(1).replace(",", ""))
                    if 100 <= n <= 100_000:
                        facts.volunteers = n
                except ValueError:
                    pass
            else:
                vm2 = re.search(r"([\d,]{3,6})\s+volunteers", text, re.I)
                if vm2:
                    try:
                        n = int(vm2.group(1).replace(",", ""))
                        if 100 <= n <= 100_000:
                            facts.volunteers = n
                    except ValueError:
                        pass

            # Charity total → spectators are rarely published; skip.

    # ------------------------------------------------------------------
    def _extract_edition(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.osaka-marathon.com/2026/expo/outline/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"第\s*(\d{1,3})\s*回\s*大阪マラソン", text)
        if m:
            try:
                facts.edition = int(m.group(1))
            except ValueError:
                pass
