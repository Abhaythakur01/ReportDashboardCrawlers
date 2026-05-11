"""TCS Toronto Waterfront Marathon — https://www.torontowaterfrontmarathon.com/

37th edition scheduled for 2026-10-17/18. The race has been held every
October since 1990 and is organised by Canada Running Series; TCS
(Tata Consultancy Services) is the title sponsor, joining the race in
the late-2010s.

Pulls:
  - / (homepage) → sponsor section. The sponsor strip uses numbered
    filenames (``1-300x300.png``, ``2-300x300.png``…) with empty alt
    text, so the scraper layers a documented partner roster on top of
    the few brand-identifiable logos that do surface in the HTML
    (CanPrev, Nespresso, Wawanesa, Flair, Made With Local, TCS).
  - /blog/ → 5 most recent articles relevant to the 2025 / 2026 edition.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Tuple

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


# Filename substring → clean brand. Lowercase keys; first match wins.
# These are the brand-identifiable logos that surface in static HTML.
_FILE_BRAND_MAP: list[tuple[str, str]] = [
    ("tcs_newlogo",        "TCS (Tata Consultancy Services)"),
    ("canprev",            "CanPrev"),
    ("nespresso",          "Nespresso"),
    ("wawanesa",           "Wawanesa Insurance"),
    ("jstw_sponsorships",  "Wawanesa Insurance"),
    ("flair",              "Flair Airlines"),
    ("mwl_logo",           "Made With Local"),
    ("chiquita",           "Chiquita"),
]

# Documented partner roster (2026). Acts as a fallback: many of the
# homepage's sponsor logos are filename-numbered (1-300x300.png …)
# with empty alt text, so we cannot identify them from HTML alone.
_DOCUMENTED_PARTNERS = [
    "ASICS",
    "Running Room",
    "Organika",
    "Garmin",
    "The Running Physio",
    "Wawanesa Insurance",
    "Liberte",
    "CanPrev",
    "Nespresso",
    "Voltaren",
    "GU Energy",
    "Oasis",
    "SunRype",
    "Sparkling Ice",
    "Subaru",
    "Flair Airlines",
    "Made With Local",
    "Shokz",
    "Chiquita",
    "Abbott World Marathon Majors",
]

_HIGHLIGHT_KEYWORDS = (
    "marathon", "tcs", "toronto", "waterfront", "kenyan", "canadian",
    "elite", "championship", "schedule", "race weekend", "pidhoresky",
    "flanagan", "kiptoo", "walk", "training",
)


@register("tcs-toronto-waterfront-marathon")
class TCSTorontoScraper(BaseScraper):
    official_url = "https://www.torontowaterfrontmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Canada Running Series",
            title_sponsor="TCS (Tata Consultancy Services)",
            edition=37,           # first held 1990 → 2026 is 37th
            inception_year=1990,
            notes="Race scheduled 2026-10-17/18; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        seen: set[str] = set()
        ordered: list[str] = []

        if soup is not None:
            # Anchor on the "Sponsors" heading; collect filename-mapped
            # brands from imgs that follow.
            anchor = None
            for h in soup.find_all(["h2", "h3", "h4"]):
                t = h.get_text(" ", strip=True).lower()
                if t == "sponsors" or t.startswith("title sponsor"):
                    anchor = h
                    break
            if anchor is not None:
                for el in anchor.find_all_next():
                    if el.name in {"h2", "h3"} and el is not anchor:
                        t = el.get_text(" ", strip=True).lower()
                        if "sponsor" not in t and "partner" not in t and "title" not in t:
                            break
                    if el.name != "img":
                        continue
                    src = (el.get("src") or "").rsplit("/", 1)[-1].split("?")[0].lower()
                    brand = self._brand_for(src)
                    if brand and brand not in seen:
                        seen.add(brand)
                        ordered.append(brand)

        # Layer documented partners on top so the report still lists
        # the sponsors whose logos are numbered placeholders in HTML.
        for brand in _DOCUMENTED_PARTNERS:
            if brand not in seen:
                seen.add(brand)
                ordered.append(brand)

        # Title sponsor split out from other_sponsors.
        title_keys = {"tcs (tata consultancy services)", "tcs"}
        others = [b for b in ordered if b.lower() not in title_keys]
        facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        soup = self.get("https://www.torontowaterfrontmarathon.com/blog/")
        if soup is None:
            return

        skip_slugs = {
            "blog", "about", "media", "partnerships", "event-info",
            "race-weekend", "race-expo", "volunteers-staff",
            "charity-challenge", "contact", "elites-and-awards",
            "womens-training-program",
        }
        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 22 or len(text) > 220:
                continue
            full = href if href.startswith("http") else (
                "https://www.torontowaterfrontmarathon.com" + href
            )
            if "torontowaterfrontmarathon.com" not in full:
                continue
            slug = full.split("#", 1)[0].rstrip("/").rsplit("/", 1)[-1]
            if not slug or slug in skip_slugs:
                continue
            # Skip the bare homepage / domain root (slug == hostname).
            if slug == "torontowaterfrontmarathon.com" or slug == "www.torontowaterfrontmarathon.com":
                continue
            if "/event-info" in full or "?" in full:
                continue
            # Require the article slug to look like a hyphenated post.
            if "-" not in slug or len(slug) < 24:
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
    @staticmethod
    def _brand_for(filename: str) -> str:
        for needle, brand in _FILE_BRAND_MAP:
            if needle in filename:
                return brand
        return ""
