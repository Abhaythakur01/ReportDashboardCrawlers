"""TCS London Marathon — https://www.tcslondonmarathon.com/

Deep scraper. The site redirects to londonmarathonevents.co.uk; both are
operated by London Marathon Events Ltd, so the host check is widened
to also accept londonmarathonevents.co.uk.

Pulls from:
  - homepage: partner outbound links (each partner has a logo with an
    external href to the partner's own domain — that's how we identify
    them, because the img alts are blank)
  - /news listing: latest articles (highlights)
  - article pages: regex-based podium extraction
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Domain → friendly brand name mapping. Anything not here is excluded.
PARTNER_DOMAIN_MAP = {
    "www.tcs.com": ("Tata Consultancy Services (TCS)", True),  # title sponsor
    "www.newbalance.co.uk": ("New Balance", False),
    "www.abbott.co.uk": ("Abbott", False),
    "www.apple.com": ("Apple", False),
    "www.buxtonwater.co.uk": ("Buxton Water", False),
    "eu.clifbar.com": ("Clif", False),
    "coopah.com": ("Coopah", False),
    "enthuse.com": ("Enthuse", False),
    "www.flora.com": ("Flora", False),
    "www.ford.co.uk": ("Ford", False),
    "www.getpro.co.uk": ("GetPro", False),
    "www.hubspot.com": ("HubSpot", False),
    "www.lucozade.com": ("Lucozade", False),
    "marathontours.com": ("Marathon Tours International", False),
    "www.radox.co.uk": ("Radox", False),
    "sportstoursinternational.co.uk": ("Sports Tours International", False),
    "www.tagheuer.com": ("TAG Heuer", False),
    "www.vaseline.com": ("Vaseline", False),
    "www.voltarol.co.uk": ("Voltarol", False),
}

_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2}:\d{2})\b")

# "59,830 people completing the event" / "59,830 runners crossed the Finish Line"
_FINISHERS_RE = re.compile(
    r"([\d,]{5,8})\s+(?:people\s+completing|runners?\s+crossed|finishers?|"
    r"runners?\s+complet(?:ing|ed)|people\s+finished)",
    re.I,
)
# Require explicit "of/from <Country>" or "<Country>'s <Name>" — avoids
# matching pronoun phrases like "his marathon".
_NAME_OF_COUNTRY_RE = re.compile(
    r"([A-Z][\w'’\-]{2,}(?:\s+[A-Z][\w'’\-]{2,}){1,3})\s+of\s+"
    r"(Kenya|Ethiopia|Uganda|Tanzania|Great Britain|United States|Netherlands|"
    r"Eritrea|Bahrain|Israel|Japan|China|Germany|France|Italy|Spain|Portugal|"
    r"South Africa|Australia|Canada|Norway|Sweden|Morocco)"
)
_COUNTRYS_NAME_RE = re.compile(
    r"(Kenya|Ethiopia|Uganda|Tanzania|Great Britain|United States|Netherlands|"
    r"Eritrea|Bahrain|Israel|Japan|China|Germany|France|Italy|Spain|Portugal|"
    r"South Africa|Australia|Canada|Norway|Sweden|Morocco)['’]s\s+"
    r"([A-Z][\w'’\-]{2,}(?:\s+[A-Z][\w'’\-]{2,}){1,3})"
)
_COUNTRY_TO_ISO = {
    "Kenya": "KEN", "Ethiopia": "ETH", "Uganda": "UGA", "Tanzania": "TAN",
    "Great Britain": "GBR", "United States": "USA", "Netherlands": "NED",
    "Eritrea": "ERI", "Bahrain": "BRN", "Israel": "ISR", "Japan": "JPN",
    "China": "CHN", "Germany": "GER", "France": "FRA", "Italy": "ITA",
    "Spain": "ESP", "Portugal": "POR", "South Africa": "RSA",
    "Australia": "AUS", "Canada": "CAN", "Norway": "NOR", "Sweden": "SWE",
    "Morocco": "MAR",
}


@register("tcs-london-marathon")
class TCSLondonScraper(BaseScraper):
    official_url = "https://www.tcslondonmarathon.com/"

    def __init__(self, official_url: str | None = None) -> None:
        super().__init__(official_url)
        # The site redirects all traffic to londonmarathonevents.co.uk —
        # also operated by London Marathon Events Ltd. Whitelist it.
        self._extra_origins = {"www.londonmarathonevents.co.uk"}

    def _check_url(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if host == self._allowed_origin or host.endswith("." + self._allowed_origin):
            return
        if host in self._extra_origins:
            return
        from app.scrapers.base import OfficialSiteOnly
        raise OfficialSiteOnly(
            f"Refusing to fetch {url}: host {host!r} not in official origins"
        )

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="London Marathon Events Ltd",
            inception_year=1981,
            edition=datetime.now().year - 1981 + 1,
            title_sponsor="Tata Consultancy Services (TCS)",
        )

        # --- 1. Homepage: partner outbound links (the only reliable signal) ---
        home = self.get(self.official_url)
        partners: List[str] = []
        if home is not None:
            seen: set[str] = set()
            for a in home.find_all("a", href=True):
                href = a["href"]
                if not href.startswith("http"):
                    continue
                host = urlparse(href).netloc.lower()
                mapping = PARTNER_DOMAIN_MAP.get(host)
                if mapping is None:
                    continue
                name, is_title = mapping
                if name in seen:
                    continue
                seen.add(name)
                if is_title:
                    facts.title_sponsor = name
                    continue
                partners.append(name)
        facts.other_sponsors = "\n".join(partners)

        # --- 2. News listing: highlights (top 5 articles) ---
        news_base = "https://www.londonmarathonevents.co.uk/"
        news_soup = self.get(news_base + "news")
        article_urls: List[Tuple[str, str]] = []
        if news_soup is not None:
            for h in news_soup.select("h3"):
                title = h.get_text(" ", strip=True)
                if not title or "our sites" in title.lower():
                    continue
                # find ancestor anchor
                a = None
                anc = h
                for _ in range(5):
                    anc = anc.parent if anc.parent else None
                    if anc is None:
                        break
                    cand = anc.find("a", href=True)
                    if cand and "/article/" in cand.get("href", ""):
                        a = cand
                        break
                if a is None:
                    continue
                href = urljoin(news_base, a["href"])
                article_urls.append((title, href))
        for title, href in article_urls[:5]:
            facts.highlights.append((title, href))

        # --- 3. Best-effort podium from the most relevant article ---
        for title, href in article_urls:
            tlow = title.lower()
            if any(k in tlow for k in ("two-hour", "sub-two", "sawe", "winner", "champion", "results")):
                self._extract_podium(href, facts)
                if facts.mens_podium or facts.womens_podium:
                    break

        # --- 4. Finisher count from the latest fundraising/recap article ---
        self._extract_finishers(article_urls, facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_finishers(self, article_urls: list, facts: RaceFacts) -> None:
        """Pull the headline finisher count from the most recent year's
        post-race recap. London publishes a ``finishers`` Guinness World
        Record every year (e.g. "59,830 people completing the event"
        for 2026), and the same fundraising / by-the-numbers articles
        repeat the figure prominently.
        """
        if facts.finishers_total is not None:
            return
        # Prefer fundraising / record-themed articles where the headline
        # count is repeated several times in the body copy.
        priority_keys = (
            "world record", "world recording", "fundraising", "by-the-numbers",
            "results", "recap", "thank you",
        )
        ordered = sorted(
            article_urls,
            key=lambda c: 0 if any(k in c[0].lower() for k in priority_keys) else 1,
        )
        for _title, href in ordered[:6]:
            soup = self.get(href)
            if soup is None:
                continue
            body = " ".join(
                p.get_text(" ", strip=True) for p in soup.find_all("p")
            )
            m = _FINISHERS_RE.search(body)
            if not m:
                continue
            try:
                n = int(m.group(1).replace(",", ""))
            except ValueError:
                continue
            # Marathon-scale sanity floor + ceiling.
            if 10_000 <= n <= 200_000:
                facts.finishers_total = n
                return

    def _extract_podium(self, url: str, facts: RaceFacts) -> None:
        """Find named athletes and their times in this article.

        Strict matching (Name of Country / Country's Name) — false
        positives are worse than missing entries because the report
        prints them verbatim.
        """
        soup = self.get(url)
        if soup is None:
            return
        text = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))

        # Build a list of (position, name, country) candidates.
        candidates: List[Tuple[int, str, str]] = []
        for m in _NAME_OF_COUNTRY_RE.finditer(text):
            candidates.append((m.start(), m.group(1).strip(), _COUNTRY_TO_ISO.get(m.group(2), "")))
        for m in _COUNTRYS_NAME_RE.finditer(text):
            candidates.append((m.start(), m.group(2).strip(), _COUNTRY_TO_ISO.get(m.group(1), "")))
        if not candidates:
            return

        # Match each candidate to the nearest H:MM:SS within ±150 chars.
        times = [(m.start(), m.group(1)) for m in _TIME_RE.finditer(text)]
        seen: set[str] = set()
        used_times: set[int] = set()
        entries: List[PodiumEntry] = []
        for pos, name, country in candidates:
            best_t = None
            best_d = 10**9
            for t_pos, t in times:
                if t_pos in used_times:
                    continue
                d = abs(t_pos - pos)
                if d < best_d:
                    best_d, best_t = d, (t_pos, t)
            if best_t is None or best_d > 150:
                continue
            if name in seen:
                continue
            seen.add(name)
            used_times.add(best_t[0])
            entries.append(PodiumEntry(rank=len(entries) + 1, name=name, nationality=country, timing=best_t[1]))
            if len(entries) == 3:
                break

        if entries:
            facts.mens_podium = entries
