"""Seoul Marathon — https://seoul-marathon.com/

The Seoul Marathon (서울마라톤), also known as the Dong-A Marathon
(동아마라톤), is one of the oldest annual marathons in Asia. Founded
in 1931 by the Dong-A Ilbo newspaper. The 2026 edition is the 96th
Dong-A Marathon (the official site references the 2027 edition as
the 97th).

Pulls (best-effort; the site is largely XE-based with sparse static
markup):
  - / (homepage)   -> sponsor/partner logos via outbound-host whitelist
  - /96            -> About / overview page (edition + organizers)
  - /81            -> News / 공지사항 page (top 5 highlights)
  - /94            -> Announcements (fallback for highlights)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Outbound host -> (clean brand, tier). 0 = title, 1 = official partner.
_SPONSOR_HOST_MAP: dict[str, tuple[str, int]] = {
    "www.adidas.co.kr": ("Adidas", 0),
    "adidas.co.kr": ("Adidas", 0),
    "shop.adidas.co.kr": ("Adidas", 0),
    "www.donga.com": ("Dong-A Ilbo", 1),
    "donga.com": ("Dong-A Ilbo", 1),
    "www.seoul.go.kr": ("Seoul Metropolitan Government", 1),
    "seoul.go.kr": ("Seoul Metropolitan Government", 1),
    "www.kasa.or.kr": ("Korea Athletics Association", 1),
    "kasa.or.kr": ("Korea Athletics Association", 1),
    "channela.com": ("Channel A", 1),
    "www.channela.com": ("Channel A", 1),
}

# Korean and English news keywords for filtering anchor text on /81 etc.
_NEWS_KEYWORDS = (
    "마라톤", "서울", "동아", "공지", "기록",
    "marathon", "seoul", "donga", "platinum", "record",
)


@register("seoul-marathon")
class SeoulMarathonScraper(BaseScraper):
    official_url = "https://seoul-marathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Seoul Marathon Organizing Committee, Dong-A Ilbo, "
                "Korea Athletics Association"
            ),
            title_sponsor="Adidas",
            inception_year=1931,
            edition=96,  # 2027 = 97th per the official site, so 2026 = 96th.
        )

        self._extract_sponsors(facts)
        self._extract_overview(facts)
        self._extract_highlights(facts)
        self._extract_overview_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
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
    def _extract_overview(self, facts: RaceFacts) -> None:
        soup = self.get("https://seoul-marathon.com/96")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        # 제 97회 동아마라톤  ->  97
        m = re.search(r"제\s*(\d{1,3})\s*회\s*동아마라톤", text)
        if m:
            try:
                ref_edition = int(m.group(1))
                # The /96 page is the 2027 race overview that announces the
                # 97th edition; the 2026 race we scrape for is the 96th.
                # If site is updated mid-season, prefer ref_edition - 1.
                if ref_edition >= 95:
                    facts.edition = ref_edition - 1
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_overview_stats(self, facts: RaceFacts) -> None:
        """The Seoul Marathon site is XE-based with sparse static
        content. Scan whatever the homepage and overview page expose
        for participant counts (참가자 X명), volunteers (자원봉사 X명),
        prize money (상금 / 우승 상금), and gender split if surfaced."""
        for url in (
            self.official_url,
            "https://seoul-marathon.com/96",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)

            # Korean and English participant patterns
            if facts.finishers_total is None:
                for pat in (
                    r"참가자\s*[:：]?\s*(?:약)?\s*([\d,]{4,6})\s*[명人]",
                    r"([\d,]{4,7})\s+(?:runners|participants|finishers)",
                ):
                    m = re.search(pat, text, re.I)
                    if m:
                        try:
                            n = int(m.group(1).replace(",", ""))
                        except ValueError:
                            continue
                        if 5_000 <= n <= 100_000:
                            facts.finishers_total = n
                            break

            # Prize money — published in KRW or USD on press blurbs.
            if facts.prize_money_usd is None:
                m = re.search(
                    r"(?:총\s*)?상금\s*[:：]?\s*(?:USD|US\$|\$)\s*([\d,]{4,9})",
                    text,
                    re.I,
                )
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                        if 50_000 <= n <= 5_000_000:
                            facts.prize_money_usd = n
                    except ValueError:
                        pass

            # Volunteers
            if facts.volunteers is None:
                vm = re.search(r"자원봉사(?:자)?\s*[:：]?\s*(?:약)?\s*([\d,]{3,6})\s*[명人]", text)
                if vm:
                    try:
                        n = int(vm.group(1).replace(",", ""))
                        if 100 <= n <= 50_000:
                            facts.volunteers = n
                    except ValueError:
                        pass
                else:
                    vm2 = re.search(r"([\d,]{3,5})\s+volunteers", text, re.I)
                    if vm2:
                        try:
                            n = int(vm2.group(1).replace(",", ""))
                            if 100 <= n <= 50_000:
                                facts.volunteers = n
                        except ValueError:
                            pass

            # Spectators
            if facts.spectators is None:
                sm = re.search(r"([\d,]{3,7})\s*\+?\s+spectators", text, re.I)
                if sm:
                    try:
                        n = int(sm.group(1).replace(",", ""))
                        if 5_000 <= n <= 5_000_000:
                            facts.spectators = n
                    except ValueError:
                        pass

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        seen: set[str] = set()
        candidates: List[tuple[str, str]] = []
        for url in (
            "https://seoul-marathon.com/81",
            "https://seoul-marathon.com/94",
        ):
            soup = self.get(url)
            if soup is None:
                continue
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(" ", strip=True)
                if not text or len(text) < 6:
                    continue
                full = href if href.startswith("http") else "https://seoul-marathon.com" + href
                if "seoul-marathon.com" not in full:
                    continue
                # XE board posts use ?document_srl=NNN or /<n>/<post_id>
                if not re.search(r"document_srl=\d+|/\d{2,5}(?:/|$)", full):
                    continue
                tlow = text.lower()
                if not any(k in text or k in tlow for k in _NEWS_KEYWORDS):
                    continue
                if full in seen:
                    continue
                seen.add(full)
                candidates.append((text[:140], full))
                if len(candidates) >= 5:
                    break
            if len(candidates) >= 5:
                break
        for title, url in candidates:
            facts.highlights.append((title, url))
