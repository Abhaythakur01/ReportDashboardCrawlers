"""Generic official-site scraper.

Best-effort extractor used as the default for any race that doesn't
have a bespoke scraper. Stays inside the official origin (host check
inherited from BaseScraper) and only pulls from the race's own pages.

What it tries to extract from the homepage + a small set of in-origin
sub-pages (about, sponsors/partners, news/press, results, FAQ):

  * inception_year     — "since YYYY", "first held in YYYY", "founded YYYY"
  * edition            — "Nth edition" / "Nst/Nnd/Nrd edition"
  * finishers_total    — "X finishers/runners/participants/competitors"
  * organizers         — schema.org Organization, "organized by", footer
  * title_sponsor      — "title sponsor", "presented by", branding line
  * other_sponsors     — sponsor logo grid, "partners" section
  * highlights         — recent news article titles + URLs

The scraper degrades gracefully — every field is independently
optional. If a site doesn't expose a sponsors page, that field stays
empty and the cross-cutting fallback layer (WA / AIMS / manual
overrides) gets a chance to fill it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from app.scrapers.base import BaseScraper, RaceFacts


# --- regexes ---------------------------------------------------------------
_INCEPTION_RES = [
    re.compile(r"\bsince\s+(19\d{2}|20\d{2})\b", re.I),
    re.compile(r"\bfirst\s+(?:run|held|raced|edition)\s*(?:in)?\s+(19\d{2}|20\d{2})\b", re.I),
    re.compile(r"\bfounded\s*(?:in)?\s+(19\d{2}|20\d{2})\b", re.I),
    re.compile(r"\bestablished\s*(?:in)?\s+(19\d{2}|20\d{2})\b", re.I),
    re.compile(r"\binaugural(?:\s+edition)?\s*(?:in)?\s+(19\d{2}|20\d{2})\b", re.I),
    re.compile(r"\b(?:starting|started|begun|debut(?:ed)?)\s*(?:in)?\s+(19\d{2}|20\d{2})\b", re.I),
]

_EDITION_RES = [
    re.compile(
        r"\b(\d{1,3})(?:st|nd|rd|th)\s+(?:edition|annual|running)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:edition|annual|running)\s*[:\-]?\s*(\d{1,3})(?:st|nd|rd|th)?\b",
        re.I,
    ),
    re.compile(
        r"\bthe\s+(\d{1,3})(?:st|nd|rd|th)\s+(?:annual|edition)\b",
        re.I,
    ),
]

_FINISHERS_RES = [
    re.compile(
        r"(?:over|nearly|approximately|about|some|more\s+than)?\s*"
        r"([\d,]{3,7})\s+"
        r"(?:runners|finishers|competitors|participants|athletes|"
        r"completed|crossed\s+the\s+finish)",
        re.I,
    ),
    re.compile(
        r"([\d,]{3,7})\s+"
        r"(?:were\s+expected|registered|signed\s+up|will\s+compete|will\s+race)",
        re.I,
    ),
]

_PRIZE_RES = [
    re.compile(
        r"(?:total\s+)?prize\s+(?:money|purse|fund|pool)\s*(?:of|:)?\s*"
        r"(?:US)?\$\s*([\d,]+(?:\.\d+)?)\s*(million|m|k|thousand)?",
        re.I,
    ),
    re.compile(
        r"\$\s*([\d,]+(?:\.\d+)?)\s*(million|m|k|thousand)?\s+"
        r"(?:in\s+)?prize\s+(?:money|purse|fund|pool|cash)",
        re.I,
    ),
    re.compile(
        r"prize\s+(?:money|purse)\s+totalling\s+(?:US)?\$\s*([\d,]+(?:\.\d+)?)\s*(million|m|k|thousand)?",
        re.I,
    ),
]

_ORG_RES = [
    re.compile(
        r"\borgani[sz]ed\s+by\s+([A-Z][^.,;\n]{2,80})",
        re.I,
    ),
    re.compile(
        r"\bpromoted\s+by\s+([A-Z][^.,;\n]{2,80})",
        re.I,
    ),
]

_TITLE_SPONSOR_RES = [
    re.compile(
        r"\btitle\s+sponsor\s*[:\-]?\s*([A-Z][^.,;\n]{2,80})",
        re.I,
    ),
    re.compile(
        r"\bpresented\s+by\s+([A-Z][^.,;\n]{2,80})",
        re.I,
    ),
]

# Words that look like sponsor/organizer noise — strip these
_NOISE_PREFIX_RE = re.compile(
    r"^(?:by|the|a|an)\s+", re.I
)


# --- helpers ---------------------------------------------------------------
def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"[“”]", '"', text)
    return text


def _intify(s: str) -> Optional[int]:
    try:
        return int((s or "").replace(",", "").replace(".", "").strip())
    except (ValueError, AttributeError):
        return None


def _trim_sponsor(s: str) -> str:
    s = _clean(s)
    s = _NOISE_PREFIX_RE.sub("", s)
    # cut at common terminators
    for term in (" - ", " – ", " — ", " | ", " is ", " are ", " has ", " who ", " which "):
        i = s.lower().find(term.lower())
        if i > 0:
            s = s[:i]
            break
    return s.strip(" .;,:-")


# Schema.org JSON-LD parsing
def _scan_jsonld(soup: BeautifulSoup) -> list[dict]:
    out: list[dict] = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            payload = json.loads(tag.string or "")
        except Exception:
            continue
        if isinstance(payload, list):
            out.extend(p for p in payload if isinstance(p, dict))
        elif isinstance(payload, dict):
            if "@graph" in payload and isinstance(payload["@graph"], list):
                out.extend(p for p in payload["@graph"] if isinstance(p, dict))
            else:
                out.append(payload)
    return out


# Common in-origin paths to crawl
_PATHS_OF_INTEREST = [
    # About / history
    "/about", "/about-us", "/the-race", "/race", "/history",
    "/en/about", "/en/about-us", "/en/the-race", "/en/history",
    # Sponsors / partners
    "/sponsors", "/partners", "/our-sponsors", "/our-partners",
    "/en/sponsors", "/en/partners",
    # News / press
    "/news", "/press", "/media", "/blog",
    "/en/news", "/en/press",
    # Results
    "/results", "/en/results",
    # FAQ
    "/faq", "/en/faq",
]


def _candidate_subpaths(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Collect in-origin links that look like about/sponsors/news pages."""
    base_host = urlparse(base_url).netloc.lower()
    keywords = (
        "about", "history", "story", "race", "course",
        "sponsor", "partner", "supporter",
        "news", "press", "media", "blog", "article",
        "result", "winner", "champion", "elite",
        "organi", "promotor",
    )
    seen: set[str] = set()
    out: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        host = urlparse(full).netloc.lower()
        # only same-origin (host or subdomain)
        if host != base_host and not host.endswith("." + base_host):
            continue
        path = urlparse(full).path.lower()
        if not path or path == "/":
            continue
        label = (a.get_text(" ", strip=True) or "").lower()
        if any(k in path or k in label for k in keywords):
            if full not in seen:
                seen.add(full)
                out.append(full)
    return out[:25]  # cap exploration


# --- the scraper -----------------------------------------------------------
class GenericScraper(BaseScraper):
    """Default scraper used for any race without a bespoke scraper."""

    def __init__(self, race_id: str, official_url: str) -> None:
        # bypass the class-level race_id requirement
        self.race_id = race_id
        super().__init__(official_url=official_url)

    # ------------------------------------------------------------------
    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
        )
        notes: list[str] = []

        # 1. Try plain HTTP first
        home = self.get(self.official_url)
        used_browser = False
        if home is None:
            # SPA / mild Cloudflare? try browser path once
            home = self.get_via_browser(self.official_url)
            if home is not None:
                used_browser = True
                notes.append("Generic: used browser path for SPA/CF.")
        if home is None:
            facts.notes = "Generic: official site unreachable"
            return facts

        # Collect text blob from homepage
        homepage_text = _clean(home.get_text(" ", strip=True))[:50000]

        # 2. Schema.org JSON-LD often holds Organization / SportsEvent data
        for obj in _scan_jsonld(home):
            t = obj.get("@type") or ""
            if isinstance(t, list):
                t = " ".join(t)
            if "Event" in t or "SportsEvent" in t:
                # founder/founded year on event/series
                if not facts.inception_year:
                    for k in ("foundingDate", "startDate"):
                        v = obj.get(k) or ""
                        if (m := re.match(r"(19\d{2}|20\d{2})", str(v))):
                            yr = int(m.group(1))
                            if not facts.inception_year or yr < facts.inception_year:
                                facts.inception_year = yr
                # organizer
                org = obj.get("organizer")
                if org and not facts.organizers:
                    if isinstance(org, dict):
                        nm = org.get("name") or ""
                    elif isinstance(org, list) and org:
                        nm = ", ".join(o.get("name", "") for o in org if isinstance(o, dict))
                    else:
                        nm = str(org)
                    if nm:
                        facts.organizers = _clean(nm)[:120]
            # Don't blindly adopt Organization.name as organizer — that's
            # often just the race name itself ("Dubai Marathon"). We only
            # adopt organizer from explicit Event.organizer above.

        # 3. Apply text patterns to homepage
        self._apply_text_patterns(homepage_text, facts)

        # 4. Crawl candidate sub-pages
        candidates = _candidate_subpaths(home, self.official_url)
        # Also try common known paths even if not linked — many sites
        # have unlinked /sponsors or /press pages. 404s are silenced
        # at the BaseScraper.get layer so this doesn't spam logs.
        seen_paths = {urlparse(u).path.lower() for u in candidates}
        for p in _PATHS_OF_INTEREST:
            if p not in seen_paths:
                full = urljoin(self.official_url, p)
                candidates.append(full)

        about_text = ""
        sponsors_text = ""
        news_links: list[tuple[str, str]] = []

        for url in candidates[:18]:
            sub = self.get(url) if not used_browser else self.get(url)
            if sub is None:
                continue
            path = urlparse(url).path.lower()
            text = _clean(sub.get_text(" ", strip=True))[:30000]
            if any(k in path for k in ("about", "history", "story", "the-race", "race")):
                about_text = (about_text + " " + text)[:60000]
                self._apply_text_patterns(text, facts)
            if any(k in path for k in ("sponsor", "partner", "supporter")):
                sponsors_text = (sponsors_text + " " + text)[:60000]
                self._extract_sponsors(sub, facts)
            if any(k in path for k in ("news", "press", "media", "blog", "article")):
                self._extract_news(sub, url, news_links)

        # 5. Compose highlights from news links (top 5)
        if not facts.highlights and news_links:
            for title, url in news_links[:5]:
                facts.highlights.append((title[:160], url))

        if any([
            facts.inception_year, facts.edition, facts.finishers_total,
            facts.organizers, facts.title_sponsor, facts.other_sponsors,
            facts.highlights,
        ]):
            notes.append("Generic scraper: extracted from official site.")
        else:
            notes.append("Generic scraper: no patterns matched on official site.")

        facts.notes = " · ".join(notes)
        return facts

    # ------------------------------------------------------------------
    def _apply_text_patterns(self, text: str, facts: RaceFacts) -> None:
        if not facts.inception_year:
            for rgx in _INCEPTION_RES:
                m = rgx.search(text)
                if m:
                    yr = int(m.group(1))
                    # sanity: race year should be 1850-current
                    if 1850 <= yr <= datetime.utcnow().year:
                        facts.inception_year = yr
                        break
        if not facts.edition:
            for rgx in _EDITION_RES:
                m = rgx.search(text)
                if m:
                    n = int(m.group(1))
                    if 1 <= n <= 200:
                        facts.edition = n
                        break
        if not facts.finishers_total:
            for rgx in _FINISHERS_RES:
                m = rgx.search(text)
                if m:
                    n = _intify(m.group(1))
                    if n and 100 <= n <= 200000:
                        facts.finishers_total = n
                        break
        if not facts.prize_money_usd:
            for rgx in _PRIZE_RES:
                m = rgx.search(text)
                if m:
                    raw = (m.group(1) or "").replace(",", "")
                    suffix = (m.group(2) or "").lower() if m.lastindex and m.lastindex >= 2 else ""
                    try:
                        val = float(raw)
                    except ValueError:
                        continue
                    if suffix in ("m", "million"):
                        val *= 1_000_000
                    elif suffix in ("k", "thousand"):
                        val *= 1_000
                    val = int(val)
                    if 1_000 <= val <= 100_000_000:
                        facts.prize_money_usd = val
                        break
        if not facts.organizers:
            for rgx in _ORG_RES:
                m = rgx.search(text)
                if m:
                    facts.organizers = _trim_sponsor(m.group(1))[:120]
                    break
        if not facts.title_sponsor:
            for rgx in _TITLE_SPONSOR_RES:
                m = rgx.search(text)
                if m:
                    facts.title_sponsor = _trim_sponsor(m.group(1))[:120]
                    break

    # ------------------------------------------------------------------
    def _extract_sponsors(self, soup: BeautifulSoup, facts: RaceFacts) -> None:
        """Pull sponsor names from <img alt=...> in obvious sponsor sections."""
        names: list[str] = []
        for img in soup.find_all("img", alt=True):
            alt = (img.get("alt") or "").strip()
            if not alt or len(alt) > 60 or len(alt) < 2:
                continue
            # Skip generic images
            if any(b in alt.lower() for b in ("logo", "sponsor", "partner")):
                # extract name preceding "logo"
                cleaned = re.sub(
                    r"\b(logo|sponsor|partner|of|the)\b",
                    "",
                    alt,
                    flags=re.I,
                ).strip(" -–—|")
                if cleaned and 2 < len(cleaned) < 50:
                    names.append(cleaned)
            elif alt[0].isupper():
                # possibly a brand name as alt text
                names.append(alt)
        # Dedupe preserving order
        seen: set[str] = set()
        deduped = []
        for n in names:
            key = n.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(n)
        if deduped and not facts.title_sponsor:
            facts.title_sponsor = deduped[0][:120]
        if deduped and not facts.other_sponsors:
            facts.other_sponsors = ", ".join(deduped[1:11])[:400]

    # ------------------------------------------------------------------
    def _extract_news(
        self, soup: BeautifulSoup, base_url: str, news: list[tuple[str, str]]
    ) -> None:
        # find article/headline links — generic strategy across many CMSes
        candidates: list[tuple[str, str]] = []
        for sel in ("article a", "h2 a", "h3 a", ".news a", ".post a", ".article a"):
            for a in soup.select(sel):
                title = _clean(a.get_text(" ", strip=True))
                href = a.get("href") or ""
                if not title or len(title) < 8 or len(title) > 200:
                    continue
                full = urljoin(base_url, href)
                if any(t.lower() == title.lower() for t, _ in candidates):
                    continue
                if any(t.lower() == title.lower() for t, _ in news):
                    continue
                candidates.append((title, full))
                if len(candidates) >= 10:
                    break
            if len(candidates) >= 10:
                break
        news.extend(candidates[: max(0, 5 - len(news))])
