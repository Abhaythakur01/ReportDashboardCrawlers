"""NN Marathon Rotterdam — https://www.nnmarathonrotterdam.com/en/

Site redirects all traffic to the Dutch domain
``nnmarathonrotterdam.nl`` — same operator (Golazo Sports), so we
allowlist that origin alongside the .com.

Pulls:
  - homepage outbound partner links → sponsor list
  - homepage news cards → highlights
  - news listing → edition number / fallback highlights
  - news archive → starting places for the marathon distance
    (Golazo's "no growth in number of participants" press release
    quotes "17,000 starting places" as the cap, the closest figure
    to a finisher count that the site exposes)

Podium is not exposed on the official site (results are delegated to
ACN Timing, an external timing platform), so the scraper leaves
podium fields blank rather than fabricate them. Prize money is also
not published on the official site.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple
from urllib.parse import urljoin, urlparse

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# "17,000 starting places" / "more than 17,000 marathon runners"
_STARTERS_RE = re.compile(
    r"(?:more\s+than\s+|over\s+|approximately\s+)?"
    r"([\d,]{4,7})\s+(?:starting\s+places|marathon\s+runners|"
    r"marathon\s+participants|runners?\s+will\s+(?:run|take)|"
    r"finishers?)",
    re.I,
)


# Domains that map to a partner brand. Other outbound links are filtered.
PARTNER_DOMAIN_MAP = {
    "www.nn.nl": ("NN", True),
    "nn.nl": ("NN", True),
    "www.asics.com": ("ASICS", False),
    "www.chocomel.com": ("Chocomel", False),
    "nos.nl": ("NOS", False),
    "aa-drink.com": ("AA Drink", False),
    "www.compeed.nl": ("Compeed", False),
    "www.zalando.nl": ("Zalando", False),
    "www.zalando.com": ("Zalando", False),
    "rotterdammakeithappen.nl": ("Rotterdam Make It Happen", False),
    "upfront.nl": ("Upfront", False),
    "www.albeda.nl": ("Albeda College", False),
    "www.atletiekunie.nl": ("Atletiekunie", False),
    "www.avis.nl": ("Avis", False),
    "www.bonboncateringenevents.nl": ("Bonbon Catering & Events", False),
    "www.shokz.com": ("Shokz", False),
    "www.chiquita.com": ("Chiquita", False),
    "chiquita.com": ("Chiquita", False),
    "www.omoda.com": ("Omoda Jaecoo", False),
    "www.jaecoo.com": ("Omoda Jaecoo", False),
}


@register("nn-marathon-rotterdam")
class NNRotterdamScraper(BaseScraper):
    official_url = "https://www.nnmarathonrotterdam.com/en/"

    def __init__(self, official_url: str | None = None) -> None:
        super().__init__(official_url)
        self._extra_origins = {"nnmarathonrotterdam.nl", "www.nnmarathonrotterdam.nl"}

    def _check_url(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if host == self._allowed_origin or host.endswith("." + self._allowed_origin):
            return
        if host in self._extra_origins:
            return
        from app.scrapers.base import OfficialSiteOnly
        raise OfficialSiteOnly(f"Refusing to fetch {url}: host {host!r} not allowed")

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Golazo Sports",
            inception_year=1981,
            title_sponsor="NN",
        )

        # The .com redirects to .nl — fetch from the canonical .nl directly.
        nl_base = "https://nnmarathonrotterdam.nl/en/"
        home = self.get(nl_base) or self.get(self.official_url)

        if home is not None:
            partners: List[str] = []
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

            # Edition: news cards include "Nth edition" phrases — capture.
            home_text = home.get_text(" ", strip=True)
            m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+edition", home_text, re.I)
            if m:
                facts.edition = int(m.group(1))

            # Highlights: news cards = h3 inside article-style cards
            article_links: List[Tuple[str, str]] = []
            for h in home.select("h3"):
                title = h.get_text(" ", strip=True)
                if not title or len(title) < 10:
                    continue
                # Find ancestor anchor
                anc = h
                href = ""
                for _ in range(5):
                    anc = anc.parent if anc.parent else None
                    if anc is None:
                        break
                    a = anc.find("a", href=True)
                    if a:
                        href = urljoin(nl_base, a["href"])
                        break
                if not href or "/category/" in href or href.endswith("/news/"):
                    continue
                article_links.append((title, href))
            for title, href in article_links[:5]:
                facts.highlights.append((title, href))

            # --- Field-size lookup: scan candidate news posts that the
            # Rotterdam organiser uses to communicate the cap (e.g. the
            # "no growth in number of participants" article). ---
            self._extract_field_size(article_links, facts)

        return facts

    def _extract_field_size(self, candidates: List[Tuple[str, str]], facts: RaceFacts) -> None:
        """Resolve total marathon starters from candidate news articles.

        Priority order: posts whose title mentions participants /
        sold-out / number / runners. Stops at the first article that
        yields a plausible marathon-scale number (5k–50k).
        """
        if facts.finishers_total is not None:
            return
        priority = (
            "participant", "sold out", "no growth", "runners",
            "starters", "course", "edition",
        )
        ordered = sorted(
            candidates,
            key=lambda c: 0 if any(k in c[0].lower() for k in priority) else 1,
        )
        for _title, href in ordered[:6]:
            soup = self.get(href)
            if soup is None:
                continue
            body = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))
            m = _STARTERS_RE.search(body)
            if not m:
                continue
            try:
                n = int(m.group(1).replace(",", ""))
            except ValueError:
                continue
            if 5_000 <= n <= 50_000:
                facts.finishers_total = n
                return
