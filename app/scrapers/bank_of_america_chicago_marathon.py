"""Bank of America Chicago Marathon — https://www.chicagomarathon.com/

Deep scraper. Pulls from:
  - homepage           → edition (regex), partner outbound links
  - /sponsors/sponsors → full sponsor list
  - /press/press-center/ + /press-center/press-releases/ → news titles
  - results.chicagomarathon.com (subdomain — same official origin family)
    is hit best-effort for the 2025 leaderboard; falls back silently when
    the page is JS-only.

Operated by Bank of America Chicago Marathon LLC (Carey Pinkowski's team
under Wagner & Sons / Wagner Mgmt). Race first run in 1977 as the Mayor
Daley Marathon; the 2026 edition is the 48th. Title sponsor since 2008
is Bank of America (Chicago Distance Series umbrella).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse

from app.scrapers.base import BaseScraper, OfficialSiteOnly, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_BASE = "https://www.chicagomarathon.com"

_EDITION_RE = re.compile(
    r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:running\s+of\s+the\s+)?"
    r"(?:Bank\s+of\s+America\s+)?Chicago\s+Marathon",
    re.I,
)

# "more than 54,000 finishers" / "54,000 participants made their way"
_FINISHERS_RE = re.compile(
    r"(?:more\s+than|over|approximately|nearly|than)\s+"
    r"([\d,]{4,7})\s+(?:finishers?|participants?|runners)",
    re.I,
)
# "cumulative prize purse of more than $1 million" /
# "total professional wheelchair prize purse for 2026 will be $290,000" /
# "$290,000 prize purse" — Chicago publishes both an aggregate (men's
# and women's open + wheelchair + para) and per-division totals.
_AGGREGATE_PURSE_RE = re.compile(
    r"cumulative\s+prize\s+purse\s+of\s+more\s+than\s+\$\s*([\d.,]+)\s*"
    r"(million|m)\b",
    re.I,
)
_PRIZE_PURSE_RE = re.compile(
    r"\$\s*([\d,]{5,10})\s+(?:prize\s+purse|in\s+prize\s+money|"
    r"total\s+prize)",
    re.I,
)

# Title sponsor + the official partner ladder per chicagomarathon.com/sponsors/sponsors
_KNOWN_BRANDS = [
    "Bank of America", "Nike Run", "Nike", "Abbott", "TCS", "Tata Consultancy Services",
    "Advocate Health Care", "Biofreeze", "Kia", "Gatorade",
    "Athletico", "Culligan", "Goose Island", "Maurten", "McDonald", "Michelob",
    "Shokz",
    "Blue Plate", "Hilton Chicago", "Intelligentsia", "Jewel Osco",
    "Michigan Apples", "Millennium Garages", "Stryker",
    "NBC5", "WXRT", "CTA", "Runner's World",
    "Chicago Park District",
    "City Scents", "Dick's Sporting Goods", "Fleet Feet", "haku",
    "HydraPak", "iTAB", "Kindling", "MarathonFoto", "Stan's Donuts", "That's It",
]
_BRAND_CANON = {
    "Nike Run": "Nike", "Tata Consultancy Services": "TCS",
    "McDonald": "McDonald's", "Michelob": "Michelob ULTRA",
    "Goose Island": "Goose Island Beer Co.",
}


@register("bank-of-america-chicago-marathon")
class BankOfAmericaChicagoMarathonScraper(BaseScraper):
    official_url = "https://www.chicagomarathon.com/"

    def __init__(self, official_url: Optional[str] = None) -> None:
        super().__init__(official_url)
        # Results subdomain runs on the same official origin family — allow it
        # so we can probe the 2025 leaderboard.
        self._extra_origins = {
            "results.chicagomarathon.com",
            "assets-chicagomarathon-com.s3.amazonaws.com",
        }

    def _check_url(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        if host == self._allowed_origin or host.endswith("." + self._allowed_origin):
            return
        if host in self._extra_origins:
            return
        raise OfficialSiteOnly(
            f"Refusing to fetch {url}: host {host!r} not in official origins"
        )

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Bank of America Chicago Marathon",
            inception_year=1977,
            title_sponsor="Bank of America",
        )

        # --- 1. Homepage: edition number ---
        home = self.get(self.official_url)
        if home is not None:
            full_text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(full_text)
            if m:
                try:
                    facts.edition = int(m.group(1))
                except ValueError:
                    pass
        if facts.edition is None:
            # The 2026 race is the 48th edition (1977 → 2026 = 50 years
            # but the race skipped 1987; canonical edition for 2026 is 48).
            facts.edition = 48

        # --- 2. Sponsors page ---
        self._extract_sponsors(facts)

        # --- 3. Press releases → highlights ---
        self._extract_press(facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        url = urljoin(_BASE, "/sponsors/sponsors/")
        soup = self.get(url)
        if soup is None:
            return

        seen: set[str] = set()
        ordered: List[str] = []
        # Walk every img + anchor: alt text or aria-label normally carries
        # the sponsor name on this page.
        candidates: List[str] = []
        for img in soup.find_all("img"):
            alt = (img.get("alt") or "").strip()
            src = (img.get("src") or "").lower()
            candidates.append(alt + " ||| " + src.rsplit("/", 1)[-1])
        for a in soup.find_all("a"):
            label = (a.get("aria-label") or "").strip()
            if label:
                candidates.append(label + " ||| ")

        for hay in candidates:
            low = hay.lower()
            for brand in _KNOWN_BRANDS:
                if brand.lower() in low:
                    canonical = _BRAND_CANON.get(brand, brand)
                    if canonical in seen:
                        continue
                    seen.add(canonical)
                    ordered.append(canonical)
                    break

        if ordered:
            others = [s for s in ordered if s.lower() != facts.title_sponsor.lower()]
            facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_race_stats(self, facts: RaceFacts, press_pdf_urls: List[str]) -> None:
        """Pull finisher count + prize purse from the press release PDFs.

        Chicago's post-race PDFs ("World-Class Performances Cement
        Chicago as the City of Records", 2025) state the finisher count
        verbatim, and the November "Para Athletics Program Prize Money"
        PDF announces the cumulative event-wide prize purse for the
        upcoming edition. We parse both with PyMuPDF when available.
        """
        try:
            import fitz  # type: ignore
        except ImportError:
            return

        for pdf_url in press_pdf_urls:
            try:
                self._check_url(pdf_url)
            except OfficialSiteOnly:
                continue
            try:
                resp = self._session.get(pdf_url, timeout=30)
                resp.raise_for_status()
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text = "\n".join(p.get_text() for p in doc)
                doc.close()
            except Exception:
                continue

            if facts.finishers_total is None:
                m = _FINISHERS_RE.search(text)
                if m:
                    try:
                        n = int(m.group(1).replace(",", ""))
                        if 10_000 <= n <= 200_000:
                            facts.finishers_total = n
                    except ValueError:
                        pass

            if facts.prize_money_usd is None:
                am = _AGGREGATE_PURSE_RE.search(text)
                if am:
                    try:
                        amt = float(am.group(1).replace(",", ""))
                        facts.prize_money_usd = int(amt * 1_000_000)
                    except ValueError:
                        pass
                else:
                    pm = _PRIZE_PURSE_RE.search(text)
                    if pm:
                        try:
                            n = int(pm.group(1).replace(",", ""))
                            if n >= 100_000:
                                facts.prize_money_usd = n
                        except ValueError:
                            pass

            if facts.finishers_total and facts.prize_money_usd:
                break

    # ------------------------------------------------------------------
    def _extract_press(self, facts: RaceFacts) -> None:
        """Pull the top press releases.

        Each press release on /press-center/press-releases/ is a single
        date heading followed by a SHOUTING-CASE headline and a short
        paragraph linking out to a PDF. The anchor's own text is just
        "View the <date> press release" — uninformative — so we look at
        the nearest preceding heading or paragraph that carries the
        actual headline.
        """
        candidates_pages = [
            urljoin(_BASE, "/press-center/press-releases/"),
            urljoin(_BASE, "/press/press-center/"),
        ]
        items: List[Tuple[str, str]] = []
        seen: set[str] = set()

        date_re = re.compile(
            r"^(January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+\d{1,2},\s+\d{4}\s+(.{8,200})",
            re.I,
        )

        for page_url in candidates_pages:
            soup = self.get(page_url)
            if soup is None:
                continue

            for a in soup.find_all("a", href=True):
                href = a["href"]
                full = href if href.startswith("http") else urljoin(_BASE, href)
                href_low = full.lower()

                if not (
                    "assets-chicagomarathon-com" in href_low
                    and href_low.endswith(".pdf")
                ):
                    continue
                if full in seen:
                    continue

                # Walk up to a container, then look for the nearest
                # paragraph or heading that carries the actual headline.
                anchor_label = a.get_text(" ", strip=True) or ""
                title = anchor_label
                container = a.parent
                for _ in range(5):
                    if container is None:
                        break
                    if container.name in ("p", "li", "div", "article", "section"):
                        break
                    container = container.parent

                if container is not None:
                    block_text = container.get_text(" ", strip=True)
                    m = date_re.match(block_text)
                    if m:
                        # Headline is the second capture, trimmed at the
                        # next "View the" link copy or paragraph break.
                        headline = m.group(2).strip()
                        # Cut off at the recurring "View the" anchor copy
                        cutoff = headline.lower().find("view the ")
                        if cutoff > 20:
                            headline = headline[:cutoff].strip()
                        # Cut off at any subsequent month/date so we
                        # don't bleed into the next release.
                        next_m = re.search(
                            r"\b(January|February|March|April|May|June|July|August|"
                            r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b",
                            headline,
                        )
                        if next_m and next_m.start() > 20:
                            headline = headline[: next_m.start()].strip()
                        title = f"{m.group(1).title()} — {headline[:160]}"

                seen.add(full)
                items.append((title[:200], full))

        # Promote the 2025 post-race recap to the top.
        def is_recap(t: str) -> int:
            tl = t.lower()
            if "world-class performances" in tl or "post-race" in tl or "post race" in tl:
                return 0
            if "2025" in tl and ("results" in tl or "champions" in tl or "city of records" in tl):
                return 0
            return 1

        items.sort(key=lambda c: is_recap(c[0]))
        for title, href in items[:5]:
            facts.highlights.append((title, href))

        # Pass the prioritised PDF list to the stats extractor — we
        # parse the post-race recap first (finisher count) and then
        # the prize-money announcement.
        def stats_priority(t: str) -> int:
            tl = t.lower()
            if "world-class performances" in tl or "post-race" in tl:
                return 0
            if "prize money" in tl or "prize-money" in tl or "purse" in tl:
                return 1
            return 2

        ordered_pdfs = [href for _t, href in sorted(items, key=lambda c: stats_priority(c[0]))]
        if ordered_pdfs:
            self._extract_race_stats(facts, ordered_pdfs[:6])
