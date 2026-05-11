"""Access Bank Lagos City Marathon — https://lagoscitymarathon.com/

11th edition, scheduled 2026-02-14. Title sponsor Access Bank, organised
by Nilayo Sports Management Ltd. World Athletics Gold Label race; the
2026 edition coincides with the World Athletics Africa Running
Conference (WAARC) Lagos 2026.

The site does not publish full top-3 podium times reliably. The 2024
recap article gives the men's sweep (Sang/Cheprot/Kiptoo, all KEN); the
women's race winner is named (Kebene Chala, ETH) but 2nd/3rd are not
exposed by the page. We capture what the site exposes and leave the
rest blank rather than make up numbers.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+edition\s+of(?:\s+the)?\s+Access\s+Bank", re.I)

_HIGHLIGHT_KEYWORDS = ("lagos", "marathon", "access bank", "sang", "cheprot", "kiptoo", "chala",
                       "kenya", "ethiopia", "elite", "waarc", "running conference")

_PARTNER_TOKENS: list[tuple[str, str]] = [
    ("access bank", "Access Bank"),
    ("nilayo", "Nilayo Sports Management"),
    ("world athletics", "World Athletics"),
    ("aiims", "AIIMS"),
    ("aims", "AIMS"),
    ("seven-up", "Seven-Up Bottling Company"),
    ("seven up", "Seven-Up Bottling Company"),
    ("coca-cola", "Coca-Cola"),
    ("coca cola", "Coca-Cola"),
    ("ndlea", "NDLEA"),
    ("eko atlantic", "Eko Atlantic City"),
    ("guinness", "Guinness Nigeria"),
    ("supersport", "SuperSport"),
    ("ntp", "Nigerian Television Authority"),
]


@register("access-bank-lagos-city-marathon")
class AccessBankLagosCityMarathonScraper(BaseScraper):
    official_url = "https://lagoscitymarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Nilayo Sports Management Ltd",
            title_sponsor="Access Bank",
            inception_year=2016,
            edition=11,  # 2016 inaugural; 2025 was 10th; 2026 is 11th
        )

        home = self.get(self.official_url)
        if home is not None:
            text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(text)
            if m:
                try:
                    facts.edition = int(m.group(1))
                except ValueError:
                    pass
            self._extract_partners(home, facts)
            self._extract_highlights(home, facts)

        # Pull the 2024 recap article for podium signals
        recap = self.get("https://lagoscitymarathon.com/kenya-ethiopia-runners-win-2024-lagos-city-marathon/")
        if recap is not None:
            self._extract_recap(recap, facts)

        # Prize money lives on /prizes/ — sum the published ladders.
        self._extract_prize_money(facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Compute total purse from the published 42km elite ladder.

        Site /prizes/ page lists 42km elite athlete prizes from $50,000
        (1st) down to $4,000 (8th). Both genders paid on the same
        ladder, so total elite purse = 2 × sum-of-ladder. Nigerian
        category and 10km add to total but quoted in NGN — we focus
        on the international elite USD purse for prize_money_usd
        (it's the headline figure).
        """
        soup = self.get("https://lagoscitymarathon.com/prizes/")
        if soup is None:
            return
        article = soup.find("article") or soup.find("main") or soup
        text = article.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # Pull explicit USD amounts (e.g. "$50,000", "$4,000").
        usd_amounts = re.findall(r"\$\s*([\d,]{3,8})", text)
        values: list[int] = []
        for raw in usd_amounts:
            try:
                v = int(raw.replace(",", ""))
                if 500 <= v <= 1_000_000:
                    values.append(v)
            except ValueError:
                continue

        # The 42km elite ladder is 8 ranks, descending. Take the first
        # 8 USD figures in document order — that's the men's ladder
        # (the women's ladder is identical, paid as a duplicate).
        if len(values) >= 8:
            ladder = values[:8]
            # Sanity: the ladder must descend.
            if ladder == sorted(ladder, reverse=True):
                total_usd = sum(ladder) * 2
                if 50_000 <= total_usd <= 2_000_000:
                    facts.prize_money_usd = total_usd
                    return

        # Fallback: the homepage states "About 500,000 USD is available
        # to be won by contestants" — use that explicit total when the
        # ladder couldn't be parsed.
        home_soup = self.get(self.official_url)
        if home_soup is not None:
            home_text = home_soup.get_text(" ", strip=True)
            m = re.search(r"(?:about|approximately|over|nearly)?\s*([\d,]{4,8})\s*(?:USD|US dollars)\b", home_text, re.I)
            if m:
                try:
                    facts.prize_money_usd = int(m.group(1).replace(",", ""))
                except ValueError:
                    pass

    # ------------------------------------------------------------------
    def _extract_partners(self, soup, facts: RaceFacts) -> None:
        seen: set[str] = set()
        ordered: list[str] = []
        for img in soup.find_all("img"):
            haystack = ((img.get("alt") or "") + " " + (img.get("src") or "")).lower()
            for needle, brand in _PARTNER_TOKENS:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
        if others:
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, soup, facts: RaceFacts) -> Optional[str]:
        seen = {h[1] for h in facts.highlights}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                href = "https://lagoscitymarathon.com" + ("" if href.startswith("/") else "/") + href
            if "lagoscitymarathon.com" not in href:
                continue
            tail = href.split("lagoscitymarathon.com", 1)[-1].strip("/")
            if not tail or tail in {"news", "news/"}:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 12 or len(title) > 200:
                continue
            tlow = title.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if href in seen:
                continue
            seen.add(href)
            facts.highlights.append((title[:140], href))
            if len(facts.highlights) >= 5:
                break
        return None

    # ------------------------------------------------------------------
    @staticmethod
    def _extract_recap(soup, facts: RaceFacts) -> None:
        article = soup.find("article") or soup.find("main") or soup
        text = article.get_text("\n", strip=True)

        # Men's winner — Bernard Sang (KEN) 02:16:49 from the 2024 recap;
        # the 2nd/3rd are named (Cheprot, Kiptoo) but their times aren't
        # in the article body. We still fill name + nationality so the
        # report shows the correct podium order.
        winner_re = re.compile(
            r"Bernard\s+Sang.*?(\d{1,2}:\d{2}:\d{2})", re.I | re.S
        )
        m = winner_re.search(text)
        mens: list[PodiumEntry] = []
        if m:
            mens.append(PodiumEntry(rank=1, name="Bernard Sang", nationality="KEN", timing=m.group(1)))
            if re.search(r"Cheprot", text, re.I):
                mens.append(PodiumEntry(rank=2, name="Simon Cheprot", nationality="KEN"))
            if re.search(r"Kiptoo", text, re.I):
                mens.append(PodiumEntry(rank=3, name="Edwin Kiptoo", nationality="KEN"))
        if mens and not facts.mens_podium:
            facts.mens_podium = mens

        womens: list[PodiumEntry] = []
        if re.search(r"Kebene\s+Chala", text, re.I):
            womens.append(PodiumEntry(rank=1, name="Kebene Chala", nationality="ETH"))
        if womens and not facts.womens_podium:
            facts.womens_podium = womens
