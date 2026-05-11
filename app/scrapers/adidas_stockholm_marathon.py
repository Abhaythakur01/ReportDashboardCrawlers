"""adidas Stockholm Marathon — https://www.stockholmmarathon.se/

47th edition, scheduled for 2026-05-30. World Athletics Road Race
Label. Title sponsor is adidas; the race is officially the "adidas
Stockholm Marathon".

Pulls:
  - /start/samarbetspartners/ → partner roster. The page links every
    partner's brand site, so an outbound-host map yields clean brand
    names without depending on Swedish alt text.
  - / (homepage) → highlights via the news cards underneath the race
    countdown. Articles use Swedish slugs but the visible titles are
    Swedish too — we pass them through; English summaries don't exist
    for most posts.

The 2026 race hasn't taken place at the time of this scraper run, so
podium / finisher data isn't yet available.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Outbound host → clean partner name. Title sponsor is adidas; everyone
# else lands in "other_sponsors". Operational hosts (registration,
# results, press kit) are deliberately excluded.
_PARTNER_HOST_MAP: dict[str, str] = {
    "www.adidas.se":                   "adidas",
    "www.voltaren.se":                 "Voltaren",
    "www.toyota.se":                   "Toyota",
    "www.zeta.nu":                     "Zeta",
    "www.vastanhede.se":               "Västanhede",
    "www.ankernordics.com":            "Anker Nordics",
    "www.factormeals.se":              "Factor Meals",
    "online.fysioline.se":             "Fysioline",
    "springtime.se":                   "Springtime",
    "runnersworld.se":                 "Runner's World",
    "www.kinto-mobility.se":           "KINTO Mobility",
    "flowlifesweden.com":              "Flow Life",
    "axelsons.se":                     "Axelsons",
    "www.gih.se":                      "GIH (Swedish School of Sport and Health Sciences)",
    "treko.se":                        "Treko",
    "www.screenbolaget.se":            "Screenbolaget",
    "www.nokas.se":                    "Nokas",
    "sortera.se":                      "Sortera",
    "www.njie.com":                    "Njie",
    "angtvattbilen.se":                "Ångtvättbilen",
    "www.bravikslandet.se":            "Bråvikslandet",
    "www.visitstockholm.com":          "Visit Stockholm",
    "www.glecom.se":                   "Glecom",
    "saljpartner.com":                 "Säljpartner",
    "www.lowcaly.com":                 "Lowcaly",
    "www.knoppers.com":                "Knoppers",
    "www.enervitsport.com":            "Enervit Sport",
    "www.chiquita.com":                "Chiquita",
    "www.vitaminwell.com":             "Vitamin Well",
    "idrottsskadespecialisterna.se":   "Idrottsskadespecialisterna",
}

_OPERATIONAL_HOSTS = {
    "events.marathongruppen.se", "manage.marathongruppen.se",
    "marathongruppen.se", "registration.marathongruppen.se",
    "stockholm.r.mikatiming.com", "minimaran.se", "marathon.se",
    "stockholmmarathon.triciclo.se", "www.mynewsdesk.com",
    "worldsmarathons.com", "www.ahotu.com", "www.facebook.com",
    "www.youtube.com",
}


@register("adidas-stockholm-marathon")
class AdidasStockholmMarathonScraper(BaseScraper):
    official_url = "https://www.stockholmmarathon.se/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Hässelby SK and Spårvägens FK (Marathongruppen i Stockholm AB)",
            title_sponsor="adidas",
            edition=47,
            inception_year=1979,
            notes="Race scheduled 2026-05-30; podium data not yet available.",
        )

        self._extract_partners(facts)
        self._extract_highlights(facts)
        self._extract_prize_money(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_prize_money(self, facts: RaceFacts) -> None:
        """Sum the Stockholm Marathon prize ladders.

        ``/start/lopare/`` (the runners' info page) lists:
          - Elite top-6 USD ladder ($10,000 → $1,000)
          - Swedish National Championship (SM-klass) top-6 SEK ladder
          - Course-record breakthrough bonuses (USD)
          - Sweden's-best-time bonuses (SEK)

        We sum the elite USD ladder (paid to both genders) and the SM
        SEK ladder (also paid to both genders), then convert SEK at
        ~10.5 SEK/USD. Breakthrough bonuses are excluded — variable.
        """
        soup = self.get("https://www.stockholmmarathon.se/start/lopare/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        # Elite USD ladder: text uses "10,000 USD" suffix style.
        usd_amounts = re.findall(r"([\d,]{3,8})\s*USD\b", text)
        usd_values: list[int] = []
        for raw in usd_amounts:
            try:
                v = int(raw.replace(",", ""))
                if 500 <= v <= 50_000:
                    usd_values.append(v)
            except ValueError:
                continue

        # The first 6 in document order are the elite ladder, descending.
        elite_usd = 0
        if len(usd_values) >= 6:
            ladder = usd_values[:6]
            if all(ladder[i] > ladder[i + 1] for i in range(len(ladder) - 1)):
                elite_usd = sum(ladder)

        # SM SEK ladder: extract "<N> SEK" amounts (page format).
        sek_amounts = re.findall(r"([\d,]{3,8})\s*SEK\b", text)
        sek_values: list[int] = []
        for raw in sek_amounts:
            digits = raw.replace(",", "").replace(" ", "")
            try:
                v = int(digits)
                if 500 <= v <= 200_000:
                    sek_values.append(v)
            except ValueError:
                continue
        sm_sek = 0
        if len(sek_values) >= 6:
            ladder = sek_values[:6]
            if all(ladder[i] > ladder[i + 1] for i in range(len(ladder) - 1)):
                sm_sek = sum(ladder)

        # Both ladders are paid per gender (men + women), so multiply
        # each by 2 before totalling.
        total_usd = elite_usd * 2
        total_usd += round((sm_sek * 2) / 10.5)  # SEK → USD ≈ 10.5 SEK/USD

        if total_usd >= 20_000:
            facts.prize_money_usd = total_usd

    # ------------------------------------------------------------------
    def _extract_partners(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.stockholmmarathon.se/start/samarbetspartners/")
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            host = urlparse(href).netloc.lower()
            if host in _OPERATIONAL_HOSTS:
                continue
            brand = _PARTNER_HOST_MAP.get(host)
            if not brand or brand in seen:
                continue
            seen.add(brand)
            ordered.append(brand)
        if ordered:
            others = [b for b in ordered if b.lower() != "adidas"]
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.stockholmmarathon.se/start/adidas-running/")
        if soup is None:
            return
        seen: set[str] = set()
        candidates: List[Tuple[str, str]] = []
        # The adidas running hub is a magazine-style page where each
        # article is a long anchor with body text. Filter to article
        # slugs (>20 chars, not the standing nav routes).
        nav_slugs = {
            "premiarmilen", "premiarhalvan", "shakeoutrun-2",
            "mer-om-stockholm", "samarbetspartners",
            "historik", "historik-1979-2018", "terms-and-conditions",
        }
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 22 or len(text) > 240:
                continue
            full = href if href.startswith("http") else "https://www.stockholmmarathon.se" + href
            if "stockholmmarathon.se" not in full or full in seen:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug or len(slug) < 20 or slug in nav_slugs:
                continue
            if any(token in full for token in ("/start/", "wp-content", "/lopet/", "/tjanster/")):
                if not re.search(r"/[a-z][a-z0-9\-]{20,}/?$", full):
                    continue
            seen.add(full)
            candidates.append((text[:180], full))
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
