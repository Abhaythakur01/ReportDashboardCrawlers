"""Durban International Marathon — https://durbanmarathon.co.za/

6th edition, 2026-05-03. The race has no commercial title sponsor —
it's organised by Newlands Athletic Club and incorporates the ASA
National Marathon Championship. Distances: 42.2 km + 10 km.

Pulls:
  - / (homepage) → sponsor logos. Most have generic alt text
    ("Sponsor Logo1") so the scraper layers a filename-substring map on
    top of the alt text to surface clean brand names.
  - /news/ → highlights, with the post-race recap lifted to highlight 1.
  - The recap article ("…shatters record at 2026 Durban International
    Marathon") carries men's + women's podiums in a flat list at the
    bottom; nationalities are inferred from the prose preceding it.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional, Tuple

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Map from a substring of either img alt text or src filename to a
# clean brand name. Keep keys lowercase.
_LOGO_TOKEN_MAP: list[tuple[str, str]] = [
    ("world athletics", "World Athletics"),
    ("biddulphs", "Biddulphs"),
    ("raf", "Road Accident Fund"),
    ("3.25 switch", "DrinkSwitch"),
    ("wanda", "Wanda Group"),
    ("asa", "Athletics South Africa"),
    ("webtickets", "Webtickets"),
]

_NATIONALITY_PATTERNS = [
    (re.compile(r"\bEthiopia['’]s\s+([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+)*)", re.I), "ETH"),
    (re.compile(r"\bKenya['’]s\s+([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+)*)", re.I), "KEN"),
    (re.compile(r"\bSouth African\s+([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+)*)", re.I), "RSA"),
    (re.compile(r"\bUgandan\s+([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+)*)", re.I), "UGA"),
    (re.compile(r"\bNamibian\s+([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+)*)", re.I), "NAM"),
    # Athlete listed with a South African club affiliation (KZN Athletics,
    # Athletics Gauteng, ASA, etc.) — they're competing for South Africa.
    (
        re.compile(
            r"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){0,3}),\s*"
            r"(?:representing|running in the colours of|of)\s+"
            r"(?:Athletics Gauteng|KZN Athletics|Athletics South Africa|ASA)",
            re.I,
        ),
        "RSA",
    ),
]

_HIGHLIGHT_KEYWORDS = ("durban", "magwai", "lema", "moloi", "bothma", "marathon", "10km", "shake out", "broadcast")

# Clean podium row from recap — name [optional dash] time [optional remark]
_RECAP_LINE_RE = re.compile(
    r"^([A-Z][\w'\-’]+(?:\s+[A-Z][\w'\-’]+){1,3})\s*[–\-]?\s*(\d{1,2}:\d{2}:\d{2})(?:\s*\(([^)]+)\))?$"
)


@register("durban-international-marathon")
class DurbanMarathonScraper(BaseScraper):
    official_url = "https://durbanmarathon.co.za/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Newlands Athletic Club",
            title_sponsor="",
            edition=6,
            inception_year=2021,
        )

        self._extract_sponsors(facts)
        recap_url = self._extract_highlights(facts)
        if recap_url:
            self._extract_recap(recap_url, facts)
        self._extract_prize_purse(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_prize_purse(self, facts: RaceFacts) -> None:
        """Pull total prize purse from the dedicated 2026 article.

        The article ``/lucrative_prize_awaits_elitefield_2026-dim/``
        publishes a fixed top-5 prize ladder (R80k/45k/20k/13k/10k =
        R168,000) plus per-time-incentive bonuses. We sum the top-5
        ladder for both genders (open category is gender-equal) and
        convert ZAR → USD at a stable approximation. The result is
        stored as an integer USD.
        """
        url = "https://durbanmarathon.co.za/lucrative_prize_awaits_elitefield_2026-dim/"
        soup = self.get(url)
        if soup is None:
            return
        article = soup.find("article") or soup.find("main") or soup
        text = article.get_text("\n", strip=True)

        # Capture each "R 80 000" / "R80,000" / "R45 000.00" amount.
        # SA convention uses spaces as thousands separator; we accept
        # both that and commas. The decimal trailer (".00") is dropped.
        amounts = re.findall(r"R\s*(\d[\d ,]{2,12})(?:\.\d+)?", text)
        zar_values: list[int] = []
        for raw in amounts:
            digits = raw.replace(",", "").replace(" ", "")
            try:
                v = int(digits)
                if 1000 <= v <= 10_000_000:
                    zar_values.append(v)
            except ValueError:
                continue

        if not zar_values:
            return

        # The first five amounts in document order are the open-
        # category top-5 ladder (R80k / R45k / R20k / R13k / R10k =
        # R168,000). The article frames this as the "open category"
        # so we don't double for separate men/women — that ladder is
        # the published purse. Time-incentive bonuses are excluded
        # (variable; paid only on hit).
        top5 = zar_values[:5]
        if len(top5) < 5:
            return
        if not (top5[0] > top5[1] > top5[2] > top5[3] > top5[4]):
            return  # not a descending ladder
        total_zar = sum(top5)

        # ZAR → USD at ~R18.5/USD. Coarse but stable for a report-level
        # figure; precision isn't the point.
        usd = round(total_zar / 18.5)
        if 5_000 <= usd <= 1_000_000:
            facts.prize_money_usd = usd

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        soup = self.get(self.official_url)
        if soup is None:
            return
        anchor = None
        for h in soup.find_all(["h2", "h3"]):
            if "sponsor" in h.get_text(" ", strip=True).lower():
                anchor = h
                break
        if anchor is None:
            return

        seen: set[str] = set()
        ordered: list[str] = []
        for el in anchor.find_all_next():
            if el.name in {"h2", "h3"} and el is not anchor:
                break
            if el.name != "img":
                continue
            alt = (el.get("alt") or "").lower()
            src = (el.get("src") or "").lower()
            haystack = alt + " " + src.rsplit("/", 1)[-1]
            for needle, brand in _LOGO_TOKEN_MAP:
                if needle in haystack and brand not in seen:
                    seen.add(brand)
                    ordered.append(brand)
                    break
        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> Optional[str]:
        soup = self.get("https://durbanmarathon.co.za/news/")
        if soup is None:
            return None

        seen: set[str] = set()
        candidates: list[Tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 12:
                continue
            full = href if href.startswith("http") else "https://durbanmarathon.co.za" + href
            if full in seen:
                continue
            if "durbanmarathon.co.za" not in full:
                continue
            if "/news/" in full or "/news?" in full:
                continue
            if "mailto:" in full or full.endswith("#") or "#" in full.split("/")[-1]:
                continue
            # Require a slug after the host
            tail = full.split("durbanmarathon.co.za", 1)[-1].strip("/")
            if not tail or "/" in tail.rstrip("/") and len(tail) < 12:
                continue
            tlow = text.lower()
            if not any(k in tlow for k in _HIGHLIGHT_KEYWORDS):
                continue
            seen.add(full)
            candidates.append((text[:120], full))

        recap_url: Optional[str] = None
        for title, url in candidates:
            if "shatters record" in title.lower() or "magwai edges" in title.lower():
                recap_url = url
                break

        # Lift recap to position 1
        if recap_url:
            candidates.sort(key=lambda c: 0 if c[1] == recap_url else 1)
        for title, url in candidates[:5]:
            facts.highlights.append((title, url))

        return recap_url

    # ------------------------------------------------------------------
    def _extract_recap(self, recap_url: str, facts: RaceFacts) -> None:
        soup = self.get(recap_url)
        if soup is None:
            return
        article = soup.find("article") or soup.find("main") or soup
        text = article.get_text("\n", strip=True)

        # Approx finisher count
        m = re.search(r"(?:close to|approximately|over|nearly)?\s*([\d,]{3,6})\s+runners", text, re.I)
        if m:
            try:
                facts.finishers_total = int(m.group(1).replace(",", ""))
            except ValueError:
                pass

        nationality_lookup = self._build_nationality_lookup(text)

        # Locate the "Men" / "Women" headers in the recap, then scan
        # subsequent lines until we leave the podium block.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        section: Optional[str] = None
        mens: List[PodiumEntry] = []
        womens: List[PodiumEntry] = []

        for ln in lines:
            low = ln.lower()
            if low == "men":
                section = "men"
                continue
            if low == "women":
                section = "women"
                continue
            if section is None:
                continue
            m = _RECAP_LINE_RE.match(ln)
            if not m:
                if section and (low.startswith("annie bothma running") or "moses mabhida" in low):
                    section = None
                continue
            name = m.group(1).strip()
            timing = m.group(2)
            remark = (m.group(3) or "").strip()
            # Men's race was a South African sweep (the recap declares so); default RSA.
            # Women's race was a mixed Ethiopian/RSA field — leave blank if not detected.
            default_nat = "RSA" if section == "men" else ""
            nat = self._lookup_nationality(name, nationality_lookup, default_nat=default_nat)
            entry = PodiumEntry(
                rank=len(mens if section == "men" else womens) + 1,
                name=name,
                nationality=nat,
                timing=timing,
                remark=remark,
            )
            if section == "men" and len(mens) < 3:
                mens.append(entry)
            elif section == "women" and len(womens) < 3:
                womens.append(entry)
            if len(mens) == 3 and len(womens) == 3:
                break

        if mens:
            facts.mens_podium = mens
        if womens:
            facts.womens_podium = womens

    # ------------------------------------------------------------------
    @staticmethod
    def _build_nationality_lookup(text: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for pat, code in _NATIONALITY_PATTERNS:
            for m in pat.finditer(text):
                surname = m.group(1).split()[-1]
                out[surname.lower()] = code
        return out

    @staticmethod
    def _lookup_nationality(name: str, lookup: dict[str, str], default_nat: str = "") -> str:
        for token in reversed(name.split()):
            t = token.strip(",.'’-").lower()
            if t in lookup:
                return lookup[t]
        return default_nat
