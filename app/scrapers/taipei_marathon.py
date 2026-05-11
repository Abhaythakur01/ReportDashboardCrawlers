"""Taipei Marathon (Dec) + New Taipei City Wan Jin Shi Marathon (Mar)

Two separate races on different sites:

* Taipei Marathon (台北馬拉松) — https://www.taipeicitymarathon.com/
  Held in Taipei City annually since 1986. The Dec 2026 edition will
  be the 41st. Organised by the Taipei City Government with the
  Taiwan Association of Athletics; Fubon Financial holds the top-tier
  sponsorship slot.

* New Taipei City Wan Jin Shi Marathon (萬金石馬拉松) —
  https://www.wanjinshi.com.tw/. Run on Taiwan's north-east coastline
  (Wanli–Jinshan–Shimen) since 1988 — the only WA-Gold-Label race in
  Taiwan. The March 2026 edition was the 28th international edition
  of the modern series. Organised by the New Taipei City Government.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_TAIPEI_BRAND_MAP: list[tuple[str, str]] = [
    ("fubon",     "Fubon Financial Holdings"),
    ("adidas",    "adidas"),
    ("herbalife", "Herbalife"),
    ("citizen",   "Citizen Watch"),
    ("pami",      "PaMi Noodles"),
    ("porsche",   "Porsche Taipei"),
    ("synmosa",   "Synmosa"),
    ("eva",       "EVA Air"),
    ("shokz",     "Shokz"),
    ("hyatt",     "Hyatt JDV"),
    ("redbull",   "Red Bull"),
    ("salonpas",  "Salonpas"),
]

# Documented partner roster (per the official site footer); used as a
# fallback when the homepage <img> srcs don't carry brand keywords.
_TAIPEI_DOCUMENTED_PARTNERS = [
    "adidas", "Herbalife", "Citizen Watch", "PaMi Noodles",
    "Porsche Taipei", "Taiwan Mobile", "Shokz", "Synmosa",
    "EVA Air", "AllSports", "Hyatt JDV", "Red Bull", "Salonpas",
]


@register("taipei-marathon")
class TaipeiMarathonScraper(BaseScraper):
    official_url = "https://www.taipeicitymarathon.com/"

    def scrape(self) -> RaceFacts:
        # The site rejects the base User-Agent with 406 — pretend to be Chrome.
        self._session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
        )

        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Taipei City Government, Taiwan Association of Athletics, SportsNet",
            title_sponsor="Fubon Financial Holdings",
            edition=41,           # 1st edition 1986; 2026 = 41st
            inception_year=1986,
        )
        # Layer documented partners as a baseline so the report has data
        # even when the dynamic sponsor strip isn't in the static HTML.
        facts.other_sponsors = "\n".join(_TAIPEI_DOCUMENTED_PARTNERS)

        soup = self.get(self.official_url) or self.get_via_browser(
            self.official_url, wait_after_load_ms=4000
        )
        if soup is None:
            return facts
        self._extract_sponsors(soup, facts)
        self._extract_news(soup, facts)
        self._extract_volunteers(facts)
        self._extract_field_size(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_volunteers(self, facts: RaceFacts) -> None:
        """Read the volunteer recruitment cap off /Volunteers.php.

        The 2025 page advertises ``預計招募654名`` (planning to recruit
        654 volunteers) — the recruitment cap is the closest the site
        publishes to a deployed-volunteer headcount.
        """
        soup = self.get(self.official_url + "Volunteers.php")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"招募\s*(\d{2,5})\s*名", text)
        if m and facts.volunteers is None:
            try:
                v = int(m.group(1))
                if 50 <= v <= 10000:
                    facts.volunteers = v
            except ValueError:
                pass

    # ------------------------------------------------------------------
    def _extract_field_size(self, facts: RaceFacts) -> None:
        """Read the field size and prize purse off /about.php and /rules.php.

        The institutional ``about.php`` page narrates the most recent
        edition: ``正式賽將有2萬8,000名跑者參賽`` (28,000 runners on
        race day). The rules page enumerates the marathon elite purse
        (top-10 men and women, in USD, identical scales) which sums to
        roughly USD 360k for the marathon distance.
        """
        about = self.get(self.official_url + "about.php")
        if about is not None:
            text = about.get_text(" ", strip=True)
            m = re.search(r"2萬\s*8,?000\s*名", text)
            if m and facts.finishers_total is None:
                facts.finishers_total = 28000
            else:
                # fall back to other big-number forms (e.g. ``2萬5,000名``)
                m2 = re.search(r"(\d)\s*萬\s*(\d[,\d]*)?\s*名\s*跑者", text)
                if m2 and facts.finishers_total is None:
                    wan = int(m2.group(1))
                    rest = m2.group(2) or "0"
                    rest_n = int(rest.replace(",", "")) if rest else 0
                    val = wan * 10000 + rest_n
                    if 5000 <= val <= 60000:
                        facts.finishers_total = val

        rules = self.get(self.official_url + "rules.php")
        if rules is not None and facts.prize_money_usd is None:
            text = rules.get_text(" ", strip=True)
            usd_amounts = []
            for m in re.finditer(r"USD\s*([\d,]+)", text):
                try:
                    n = int(m.group(1).replace(",", ""))
                    if 100 <= n <= 200000:
                        usd_amounts.append(n)
                except ValueError:
                    pass
            # Marathon top-10 published as a single ladder (1st through
            # 10th place). Apply both genders by doubling since the
            # rules page states "男子組及女子組選手相同獎金額度"
            # (men's and women's prize money is identical). The first 10
            # numbers correspond to the men's ladder (record bonus is
            # the published 1st-place value); the same ladder applies
            # to women.
            if len(usd_amounts) >= 10:
                ladder = usd_amounts[:10]
                # Drop the record-bonus duplicate (USD 100,000 twice
                # for record-breaking men's and women's first place);
                # keep "未破紀錄者 USD90,000" as the standard 1st-place
                # value when the record-bonus pair appears first.
                if (
                    ladder[0] == ladder[1] == 100000
                    and len(usd_amounts) >= 11
                    and usd_amounts[2] in (90000, 100000)
                ):
                    ladder = [usd_amounts[2]] + usd_amounts[3:11]
                purse_one_gender = sum(ladder)
                facts.prize_money_usd = purse_one_gender * 2

    # ------------------------------------------------------------------
    def _extract_sponsors(self, soup, facts: RaceFacts) -> None:
        seen: set[str] = set(_TAIPEI_DOCUMENTED_PARTNERS)
        ordered: list[str] = list(_TAIPEI_DOCUMENTED_PARTNERS)
        for img in soup.find_all("img"):
            src = (img.get("src") or "").lower()
            alt = (img.get("alt") or "").lower()
            haystack = src.rsplit("/", 1)[-1] + " " + alt
            for needle, brand in _TAIPEI_BRAND_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [b for b in ordered if b != "Fubon Financial Holdings"]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_news(self, soup, facts: RaceFacts) -> None:
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 10 or len(text) > 220:
                continue
            if "news-page" not in href and "news" not in href.lower():
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + "/" + href.lstrip("/")
            if "taipeicitymarathon.com" not in full or full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))


@register("new-taipei-city-wan-jin-shi-marathon")
class WanJinShiMarathonScraper(BaseScraper):
    official_url = "https://www.wanjinshi.com.tw/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="New Taipei City Government, Chinese Taipei Athletic Association",
            title_sponsor="",
            edition=28,           # International (modern) era; tracing to 1988.
            inception_year=1988,
            notes="Official domain often unreachable; podium via WA fallback.",
        )
        soup = self.get(self.official_url) or self.get_via_browser(
            self.official_url, wait_after_load_ms=4000
        )
        if soup is None:
            return facts
        seen: set[str] = set()
        for a in soup.find_all("a", href=True)[:200]:
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12 or len(text) > 200:
                continue
            full = href if href.startswith("http") else self.official_url.rstrip("/") + "/" + href.lstrip("/")
            if "wanjinshi.com.tw" not in full or full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:140], full))
            if len(facts.highlights) >= 5:
                break
        return facts
