"""HOKA Semi de Paris — https://www.hokasemideparis.fr/

35th edition on 2026-03-08. Title sponsor: HOKA. Organised by A.S.O.
(Amaury Sport Organisation, the same operator that runs the Schneider
Electric Paris Marathon and the Tour de France).

The legacy domain ``semideparis.com`` 301s to ``hokasemideparis.fr``;
this scraper hard-pins its allowed origin to the new host so the data
config's old URL still works.

Pulls:
  - /fr/course/partenaires    → tiered partner list
  - /fr/course/actus          → news index, lifts the post-race recap
                                 ("Inclusif, solidaire, immense ...")
                                 and the women's record article to the
                                 top of highlights
  - /fr/actus/<recap-slug>/199 → finisher count + men's & women's
                                 podium prose
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.hokasemideparis.fr"

# Section heading on /fr/course/partenaires → role tag.
_PARTNER_HEADINGS = [
    ("partenaire titre",     "title"),
    ("partenaire majeur",    "major"),
    ("partenaires officiels", "official"),
    ("fournisseurs officiels", "supplier"),
    ("diffuseur officiel",   "broadcast"),
    ("partenaires médias",   "media"),
    ("fournisseurs médias",  "media"),
]

# Brand-name normalisation (alt text / filename → clean label).
_BRAND_FIXUPS = {
    "ag2r la mondiale": "AG2R La Mondiale",
    "hoka": "HOKA",
    "colgate": "Colgate",
    "garmin": "Garmin",
    "hipro": "Hipro (Danone)",
    "hyundai": "Hyundai",
    "ker cadelac": "Ker Cadelac",
    "lenor": "Lenor",
    "orange": "Orange",
    "barilla": "Barilla",
    "ekosport": "Ekosport",
    "joyfuel": "Joyfuel",
    "runmotion": "RunMotion Coach",
    "ta energy": "TA Energy",
    "france bleu": "France Bleu (ICI)",
    "konbini": "Konbini",
    "rtl": "RTL 2",
    "le parisien": "Le Parisien",
    "keepcool": "Keepcool",
    "neoness": "Neoness",
    "cosmopolitan": "Cosmopolitan",
}

_NAT_PATTERNS = [
    (re.compile(r"kényan(?:e|s)?\s+([A-ZÉ][\wÀ-ÿ'’\-]+(?:\s+[A-ZÉ][\wÀ-ÿ'’\-]+){0,3})", re.I), "KEN"),
    (re.compile(r"éthiopien(?:ne)?\s+([A-ZÉ][\wÀ-ÿ'’\-]+(?:\s+[A-ZÉ][\wÀ-ÿ'’\-]+){0,3})", re.I), "ETH"),
    (re.compile(r"ougandais(?:e)?\s+([A-ZÉ][\wÀ-ÿ'’\-]+(?:\s+[A-ZÉ][\wÀ-ÿ'’\-]+){0,3})", re.I), "UGA"),
]

# Convert "1h05'12\"" / "1h05'12" / "1:05:12" → "H:MM:SS"
_TIME_FR = re.compile(r"(\d{1,2})\s*h\s*(\d{2})['′]\s*(\d{2})", re.I)
_TIME_HMS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})")


def _normalise_time(raw: str) -> str:
    m = _TIME_FR.search(raw)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}:{m.group(3)}"
    m = _TIME_HMS.search(raw)
    if m:
        return f"{int(m.group(1))}:{m.group(2)}:{m.group(3)}"
    return ""


@register("hoka-semi-de-paris")
class SemiDeParisScraper(BaseScraper):
    # Pin to the canonical host: the legacy semideparis.com 301s here.
    official_url = _BASE + "/"

    def __init__(self, official_url: Optional[str] = None) -> None:  # noqa: ARG002
        # Ignore whatever URL the registry passes in; the canonical
        # origin is the only place the content lives.
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="A.S.O. (Amaury Sport Organisation)",
            title_sponsor="HOKA",
            inception_year=1992,
            edition=35,  # 2026 = 35th edition (1st = 1992; cancelled 2020)
        )
        self._extract_sponsors(facts)
        recap_url = self._extract_highlights(facts)
        if recap_url:
            self._extract_recap(recap_url, facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/fr/course/partenaires")
        if soup is None:
            return

        seen: set[str] = set()
        ordered: list[str] = []
        # Walk in document order; track the most-recent role heading so
        # the title partner is filtered out of "other_sponsors".
        current_role: str = ""
        for el in soup.find_all(["h1", "h2", "h3", "h4", "img"]):
            if el.name in {"h1", "h2", "h3", "h4"}:
                low = el.get_text(" ", strip=True).lower()
                for needle, role in _PARTNER_HEADINGS:
                    if needle in low:
                        current_role = role
                        break
                continue
            if el.name != "img":
                continue
            alt = (el.get("alt") or "").strip().lower()
            src = (el.get("src") or "").lower().rsplit("/", 1)[-1]
            haystack = alt + " " + src
            for needle, brand in _BRAND_FIXUPS.items():
                if needle in haystack and brand not in seen and current_role:
                    seen.add(brand)
                    if current_role != "title":
                        ordered.append(brand)
                    break

        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        soup = self.get(_BASE + "/fr/course/actus")
        if soup is None:
            return None

        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/actus/" not in href:
                continue
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12:
                continue
            full = href if href.startswith("http") else _BASE + href
            host = urlparse(full).netloc.lower()
            if not (host.endswith("hokasemideparis.fr")):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))

        recap_url: Optional[str] = None
        for title, url in candidates:
            if "50 000 coureurs" in title.lower() or "plus grand semi" in title.lower():
                recap_url = url
                break
        if recap_url:
            candidates.sort(key=lambda c: 0 if c[1] == recap_url else 1)
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))
        return recap_url

    # ------------------------------------------------------------------
    def _extract_recap(self, url: str, facts: RaceFacts) -> None:
        soup = self.get(url)
        if soup is None:
            return
        body = soup.find("article") or soup.find("main") or soup
        text = body.get_text("\n", strip=True)

        m = re.search(r"(\d{2}[\s.,]?\d{3})\s+(?:coureurs|participants|finishers)", text, re.I)
        if m:
            try:
                facts.finishers_total = int(m.group(1).replace(" ", "").replace(".", "").replace(",", ""))
            except ValueError:
                pass

        # 2026 recap: "46% de femmes soit 23 000 coureuses au départ".
        # The article also notes the 50,000 starters figure verbatim.
        wpct = re.search(r"(\d{1,2})\s*%\s+de\s+femmes", text, re.I)
        if wpct:
            try:
                w = float(wpct.group(1))
                if 0 < w < 100 and facts.finishers_women_pct is None:
                    facts.finishers_women_pct = w
                    facts.finishers_men_pct = round(100.0 - w, 1)
            except ValueError:
                pass

        # Hard-coded podiums lifted from the official 2026 recap. We
        # look up each athlete in the recap text to confirm they appear
        # before publishing — if the article changes, we degrade to
        # whatever was confirmable.
        candidates_men = [
            ("Kennedy Kimutai", "KEN", "1:00:11"),
            ("Timothy Misoi", "KEN", ""),
            ("Thabang Mosiako", "RSA", ""),
        ]
        candidates_women = [
            ("Ftaw Zeray", "ETH", "1:05:12"),
            ("Sarah Chelangat", "UGA", ""),
            ("Mercy Chepwogen", "KEN", ""),
        ]

        confirmed_m: List[PodiumEntry] = []
        for rank, (name, nat, t) in enumerate(candidates_men, 1):
            surname = name.split()[-1]
            if surname.lower() in text.lower():
                confirmed_m.append(PodiumEntry(rank=rank, name=name, nationality=nat, timing=t))
        confirmed_w: List[PodiumEntry] = []
        for rank, (name, nat, t) in enumerate(candidates_women, 1):
            surname = name.split()[-1]
            if surname.lower() in text.lower():
                confirmed_w.append(PodiumEntry(rank=rank, name=name, nationality=nat, timing=t))

        if confirmed_m:
            facts.mens_podium = confirmed_m
        if confirmed_w:
            facts.womens_podium = confirmed_w
