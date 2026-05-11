"""Bank of America Chicago 13.1 — https://chicago13point1.com/

13th edition on 2026-06-07. Title sponsor: Bank of America. Organised
by the Chicago Distance Series team (the same operator behind the
Bank of America Chicago Marathon's parent organisation, Chicago Event
Management).

The legacy ``chicago131.com`` 301s to ``chicago13point1.com``; this
scraper hard-pins to the new host because the data config still
references the legacy domain.

Pulls:
  - /sponsors/  → tier-grouped partner list
  - /          → upcoming-edition date copy

Results:
  This race publishes timing exclusively through an off-origin tracker
  (``track.rtrt.me/e/BAHM<year>``). Because BaseScraper enforces
  same-origin fetching, podium data isn't reachable from this scraper.
  The ``_fallbacks`` layer can backfill from sanctioning-body sources
  if the race is World Athletics-listed; otherwise podium remains
  empty.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional, Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


_BASE = "https://chicago13point1.com"

# Sponsor sections on /sponsors/ → tier label. The page's H2 headings
# are short single words like "OFFICIAL", "SUPPORTING", etc., so we
# match on the leading token (case-insensitive, partial).
_SPONSOR_SECTIONS = [
    ("presenting", "title"),
    ("title",      "title"),
    ("primary",    "title"),
    ("official",   "official"),
    ("supporting", "supporting"),
    ("media",      "media"),
    ("community",  "community"),
    ("vendor",     "vendor"),
]

# Names we never want to surface even if they match.
_BAD_SPONSOR_TOKENS = {
    "loading", "image", "logo", "sponsor", "partner", "search panel",
    "skip to content", "ajax-loader",
}


@register("bank-of-america-chicago-13-1")
class Chicago131Scraper(BaseScraper):
    # Pin to the canonical origin; legacy chicago131.com 301s here.
    official_url = _BASE + "/"

    def __init__(self, official_url: Optional[str] = None) -> None:  # noqa: ARG002
        super().__init__(official_url=self.official_url)

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Chicago Event Management",
            title_sponsor="Bank of America",
            inception_year=2014,
            edition=13,  # 2026 = 13th edition (1st = 2014; cancelled 2020)
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        self._verify_edition(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(_BASE + "/sponsors/")
        if soup is None:
            return

        # The /sponsors/ page is structured as: a hero "SPONSORS" H1,
        # then the title-sponsor logo (Bank of America) appears BEFORE
        # the first section H2. Subsequent H2 headings ("OFFICIAL",
        # "SUPPORTING", "MEDIA PARTNERS", ...) precede their tier of
        # logos. We start in the implicit "title" tier and switch on
        # each H2 we recognise.
        seen: set[str] = set()
        ordered: list[str] = []
        current_role = "title"
        for el in soup.find_all(["h1", "h2", "img"]):
            if el.name in {"h1", "h2"}:
                low = el.get_text(" ", strip=True).lower().strip()
                # H1 "SPONSORS" or "You are now leaving …" → keep current state
                if not low or "sponsor" == low or low.startswith("you are"):
                    if "you are" in low:
                        current_role = ""  # leave the sponsor section entirely
                    continue
                for needle, role in _SPONSOR_SECTIONS:
                    if low.startswith(needle) or needle == low:
                        current_role = role
                        break
                continue
            if not current_role:
                continue
            alt = (el.get("alt") or "").strip()
            if not alt or len(alt) > 80:
                continue
            low = alt.lower().strip()
            if low in _BAD_SPONSOR_TOKENS:
                continue
            if low.startswith("bank of america chicago"):
                # The header/footer logo, not a sponsor entry.
                continue
            # Strip trailing " logo" tokens that appear in some alts.
            cleaned = re.sub(r"\s+logo\.?$", "", alt, flags=re.I).strip()
            cleaned = re.sub(r"\s*\.\s*$", "", cleaned).strip()
            key = cleaned.lower()
            if not key or key in seen:
                continue
            seen.add(key)
            if current_role == "title":
                # Primary tier — already stored in facts.title_sponsor.
                continue
            ordered.append(cleaned)

        if ordered:
            facts.other_sponsors = "\n".join(ordered[:30])

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        # The homepage's H2 sections each link out to a deep info page;
        # those make better highlights than the top nav. The site does
        # not publish race recaps in a /news/ directory, so we surface
        # the curated event-info anchors instead.
        soup = self.get(self.official_url)
        if soup is None:
            return
        wanted_keywords = (
            "explore the west side",
            "race day festival",
            "charity program",
            "marketing opportunities",
            "wellness fest",
            "chicago distance series",
            "course",
        )
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 14 or len(text) > 100:
                continue
            tlow = text.lower()
            if tlow in {"read more", "learn more", "find out more", "view results"}:
                continue
            full = href if href.startswith("http") else _BASE + href
            if "chicago13point1.com" not in full:
                continue
            tail = full.split("chicago13point1.com", 1)[-1].strip("/")
            if not tail or "/" not in tail:
                # Top-level nav slugs (no nested path) — skip.
                continue
            if not any(k in tlow for k in wanted_keywords):
                continue
            if full in seen:
                continue
            seen.add(full)
            candidates.append((text[:140], full))

        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

    # ------------------------------------------------------------------
    def _verify_edition(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        # Page often says "13th annual ..." or "the 13th edition".
        m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+(?:annual|edition)", text, re.I)
        if m:
            try:
                ed = int(m.group(1))
                if 1 <= ed <= 50:
                    facts.edition = ed
                    facts.inception_year = datetime.now().year - ed + 1
            except ValueError:
                pass
