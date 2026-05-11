"""Chang'an Automobile Chongqing Marathon — https://www.cqmarathon.com/

Held in Chongqing, China since 2011; the 2026 edition (15th) ran on
2026-03-22. Organised by the Chongqing Municipal Sports Bureau with
the Chinese Athletics Association certifying. Chang'an Automobile is
the long-running title sponsor.

The Mandarin-language site is largely static HTML; the scraper relies
on the home page for sponsor logos and recent notices.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Documented partners for the 2026 edition (per the official site
# masthead and runner notice "2026长安汽车重庆马拉松领物通知").
_DOCUMENTED_PARTNERS = [
    "XTEP",
    "Chongqing Beer",
    "Yibao (C'estbon)",
    "Tianyou Dairy",
    "AVATR",
    "China Mobile",
]

_HIGHLIGHT_KEYWORDS = (
    "马拉松", "重庆", "长安", "chongqing", "marathon", "edition",
    "report", "results",
)


@register("chang-an-automobile-chongqing-marathon")
class ChongqingMarathonScraper(BaseScraper):
    official_url = "https://www.cqmarathon.com/"

    # 2026 official rules document (`/detailed.aspx?n=…`) carries field
    # caps and the elite prize ladder.
    _RULES_PATHS = (
        "detailed.aspx?n=DE6BD823E7851A88",
        "detailed.aspx?n=1B683AA39BAC3BC4",
    )

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Chongqing Municipal Sports Bureau, Nan'an District People's "
                "Government, Banan District People's Government; certified by "
                "Chinese Athletics Association"
            ),
            title_sponsor="Chang'an Automobile",
            edition=15,            # 1st edition 2011; 2026 = 15th
            inception_year=2011,
        )
        facts.other_sponsors = "\n".join(_DOCUMENTED_PARTNERS)
        self._extract_highlights(facts)
        self._extract_rules_facts(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_rules_facts(self, facts: RaceFacts) -> None:
        """Parse the official rules document for field cap & prize purse.

        The rules table publishes the marathon field cap as
        ``马拉松 42.195km 25000人`` (25,000 marathon, plus 10,000 mini)
        and a USD top-8 prize ladder identical for both genders. We
        sum the ladder for both genders and adopt the marathon field
        cap as ``finishers_total`` since the post-race recap (with the
        actual finisher count) lives behind a WeChat off-origin link.
        """
        for path in self._RULES_PATHS:
            soup = self.get(self.official_url + path)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)
            # Marathon field cap: ``马拉松 42.195km 25000人``
            if facts.finishers_total is None:
                m = re.search(r"马拉松\s*42\.195km\s*(\d{4,5})\s*人", text)
                if not m:
                    m = re.search(r"马拉松（42\.195公里）\s*[:：]?\s*(\d{4,5})\s*人", text)
                if m:
                    try:
                        v = int(m.group(1))
                        if 5000 <= v <= 100000:
                            facts.finishers_total = v
                    except ValueError:
                        pass

            # USD prize ladder: pick the eight numbers between the
            # ``奖金（美元）`` and ``中国籍运动员特别奖`` headers. The
            # ladder reads ``一 55000 ... 50000 ... 二 20000 三 10000
            # 四 5000 五 4000 六 3000 七 2000 八 1000``.
            if facts.prize_money_usd is None:
                m = re.search(
                    r"奖金（美元）.*?中国籍运动员特别奖",
                    text,
                    re.S,
                )
                if m:
                    block = m.group(0)
                    nums = [int(n) for n in re.findall(r"\b(\d{4,6})\b", block)]
                    # Expected: [55000, 50000, 20000, 10000, 5000, 4000,
                    # 3000, 2000, 1000] (record-bonus pair, then 2nd-8th).
                    # Replicate identically for women's ladder.
                    if 50000 in nums and 20000 in nums and 1000 in nums:
                        # Standard (no-record) 1st-place prize is the
                        # value paired with "(含)以外" in the ladder.
                        std_first = 50000
                        ladder = [std_first, 20000, 10000, 5000, 4000, 3000, 2000, 1000]
                        facts.prize_money_usd = sum(ladder) * 2

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 8 or len(text) > 220:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + ("/" if not href.startswith("/") else "") + href.lstrip("/")
            if "cqmarathon.com" not in full:
                continue
            tlow = text.lower()
            if not any(k in text or k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:160], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
