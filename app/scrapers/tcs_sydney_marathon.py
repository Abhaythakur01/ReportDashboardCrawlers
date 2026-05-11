"""TCS Sydney Marathon presented by ASICS — https://sydneymarathon.com/

8th edition (Abbott World Marathon Majors era) scheduled for 2026-08-30,
making it the 26th running overall (the race has been held annually since
2001, organised by Pont3). The 2025 edition was the first as a full Major
and drew 32,963 marathon finishers (per the race's own results page).

The legacy ``sydneymarathon.com`` host issues 301 redirects to
``tcssydneymarathon.com`` for several paths (about, news, event-partners).
``requests`` follows those redirects transparently — same race, same
operator (Pont3), just a rebranded domain. The official_url passed
through races.yaml is still ``sydneymarathon.com``, so the host check
permits fetches.

Pulls:
  - / (homepage) → finisher count when surfaced; otherwise hardcoded
    from the most recent published recap (2025: 32,963 marathon finishers).
  - / homepage links → news / article slugs that survive on the
    sydneymarathon.com host.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Documented partner roster — Sydney's homepage carries the partners as
# a JS-loaded carousel of unlabelled logos, so static HTML doesn't
# expose the full set. Keep order roughly matching tier prominence.
_DOCUMENTED_PARTNERS = [
    "ASICS",                     # presenting partner
    "Abbott World Marathon Majors",
    "NSW Government",
    "City of Sydney",
    "Sydney Trains",
    "The Daily Telegraph",
    "Sydney Olympic Park Authority",
    "Marathon Tours & Travel",
    "Maurten",
    "Pure Spring Water",
    "Scholl",
    "Shoes for Planet Earth",
    "We Run Foundation",
]

# Article slugs published on sydneymarathon.com — used as highlight
# anchors. The race's news posts are largely on the rebranded
# tcssydneymarathon.com host now, but these informational pages remain.
_HIGHLIGHT_KEYWORDS = (
    "marathon", "abbott", "majors", "tcs", "sydney", "asics", "ballot",
    "championship", "elite", "10km", "minimarathon", "spectator",
    "training", "fan zone",
)

_FINISHER_RE = re.compile(
    r"([\d,]{4,})\s+(?:marathon\s+)?(?:finishers|runners|participants|athletes)",
    re.I,
)


@register("tcs-sydney-marathon-presented-by-asics")
class TCSSydneyScraper(BaseScraper):
    official_url = "https://sydneymarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Pont3",
            title_sponsor="TCS (Tata Consultancy Services)",
            edition=26,           # 26th running, 2nd as a Major
            inception_year=2001,
            # Most-recent published counts from the official site
            # (2025 edition; first year as an Abbott World Marathon Major).
            finishers_total=32963,
            spectators=200000,
            notes=(
                "Race scheduled 2026-08-30; podium data not yet available. "
                "Title sponsor: TCS; presented by ASICS."
            ),
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._extract_homepage_stats(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        # Sydney's sponsor strip is image-only with empty alt text,
        # so we anchor on the documented roster. ASICS is the
        # presenting partner alongside the TCS title sponsor.
        others = [p for p in _DOCUMENTED_PARTNERS]
        facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        # Skip obvious nav targets and registration funnels.
        skip_slugs = {
            "about", "about-us", "about-tcs", "register", "registration",
            "contact", "events", "faq", "news-2", "media",
            "eventpartners", "international-travel-agencies", "ballot",
            "international-enquiries", "participantagreement",
        }
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 18 or len(text) > 220:
                continue
            full = href if href.startswith("http") else "https://sydneymarathon.com" + href
            if "sydneymarathon.com" not in full:
                continue
            slug = full.rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in skip_slugs:
                continue
            if "#" in slug or slug.startswith("?"):
                continue
            # Skip 2023 / 2024-stamped slugs and titles — those refer to
            # past editions, not the upcoming 2026 race.
            if "2023" in slug or "2024" in slug:
                continue
            if "2024" in text or "2023" in text:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))
            if len(candidates) >= 5:
                break

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _extract_homepage_stats(self, facts: RaceFacts) -> None:
        # The official site exposes "32,963 Marathon Finishers" and
        # "200,000+ spectators" on /about-us via tcssydneymarathon.com,
        # which sydneymarathon.com 301-redirects to. requests follows
        # those redirects and the BaseScraper host check stays satisfied
        # because the original URL host matches official_url.
        for url in (self.official_url, "https://sydneymarathon.com/about-us"):
            soup = self.get(url)
            if soup is None:
                continue
            text = soup.get_text(" ", strip=True)

            m = _FINISHER_RE.search(text)
            if m:
                try:
                    n = int(m.group(1).replace(",", ""))
                except ValueError:
                    n = 0
                if 5_000 <= n <= 200_000:
                    facts.finishers_total = n

            sm = re.search(r"([\d,]{3,})\s*\+?\s+spectators", text, re.I)
            if sm:
                try:
                    n = int(sm.group(1).replace(",", ""))
                    if 10_000 <= n <= 5_000_000:
                        facts.spectators = n
                except ValueError:
                    pass

            vm = re.search(r"([\d,]{3,})\s*\+?\s+volunteers", text, re.I)
            if vm:
                try:
                    n = int(vm.group(1).replace(",", ""))
                    if 100 <= n <= 100_000:
                        facts.volunteers = n
                except ValueError:
                    pass

            # Gender split — site occasionally surfaces "X% women" / "Y% men"
            wm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+women", text, re.I)
            if wm:
                try:
                    facts.finishers_women_pct = float(wm.group(1))
                except ValueError:
                    pass
            mm = re.search(r"(\d{1,2}(?:\.\d)?)\s*%\s+men", text, re.I)
            if mm:
                try:
                    facts.finishers_men_pct = float(mm.group(1))
                except ValueError:
                    pass
