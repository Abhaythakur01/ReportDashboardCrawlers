"""BAA Boston Marathon — https://www.baa.org/races/boston-marathon/

Deep scraper. Pulls from:
  - homepage             → edition, news cards, key stats
  - /sponsors/           → full sponsor list, title sponsor
  - latest recap article → men's / women's podium (Open division)

Podium parsing uses regex against the official recap copy. The recap structure
is consistent year-to-year (winner highlighted with full time, runners-up with
times listed in the body), so the same selectors work for future editions.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Tuple

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


_TIME_RE = re.compile(r"\b([0-2]?\d:\d{2}:\d{2}|[0-5]\d:\d{2})\b")
_EDITION_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\s+Boston Marathon", re.I)

# "32,294 participants are entered" / "30,000 expected to run on race day"
_ENTERED_RE = re.compile(r"([\d,]{4,8})\s+participants?\s+are\s+entered", re.I)
# "18,183 Men, 13,996 Women, 115 Non-Binary Entrants"
_GENDER_SPLIT_RE = re.compile(
    r"([\d,]{3,7})\s+Men[,\s]+([\d,]{3,7})\s+Women(?:[,\s]+([\d,]{1,6})\s+Non[\s\-]?Binary)?",
    re.I,
)
# "$1,284,500 across Open, Wheelchair" — prize purse callout
_PRIZE_PURSE_RE = re.compile(
    r"\$([\d,]{5,12})\s+across\s+Open(?:[,\s]+Wheelchair)?",
    re.I,
)
# A capitalized first-or-last name phrase. 1-3 words, each starts with a capital,
# can include hyphens / apostrophes (Ngugi-Cooper, O'Brien).
_NAME_RE = re.compile(r"\b([A-Z][\w'’\-]{2,}(?:\s+[A-Z][\w'’\-]{2,}){0,2})\b")
_RANK_PHRASE_RE = re.compile(
    r"(second|third|runner-?up|runners-?up)\s+in\s+(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})",
    re.I,
)
_PAIR_TIMES_RE = re.compile(
    r"respective\s+times\s+of\s+(\d{1,2}:\d{2}:\d{2})\s+and\s+(\d{1,2}:\d{2}:\d{2})",
    re.I,
)
# "Chemnung would finish second in 2:19:35 and Ngugi-Cooper in 2:20:07"
_AND_FOLLOWUP_RE = re.compile(
    r"\b(?:second|third|runner-?up)\s+in\s+(?:\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})\s+and\s+"
    r"([A-Z][\w'’\-]{2,}(?:\s+[A-Z][\w'’\-]{2,}){0,2})"
    r"\s+in\s+(\d{1,2}:\d{2}:\d{2}|\d{1,2}:\d{2})",
    re.I,
)


@register("baa-boston-marathon")
class BAABostonScraper(BaseScraper):
    official_url = "https://www.baa.org/races/boston-marathon/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Boston Athletic Association (B.A.A.)",
            inception_year=1897,
            title_sponsor="Bank of America",
        )

        base = self.official_url if self.official_url.endswith("/") else self.official_url + "/"

        # --- 1. Homepage: edition, athlete count, volunteers, news ---
        home = self.get(base)
        if home is not None:
            full_text = home.get_text(" ", strip=True)
            m = _EDITION_RE.search(full_text)
            if m:
                facts.edition = int(m.group(1))

            # Stats panel — articles with numeric paragraph + descriptive paragraph
            for art in home.select("article"):
                ps = art.find_all("p")
                if len(ps) >= 2:
                    num_txt = ps[0].get_text(strip=True)
                    desc = ps[1].get_text(" ", strip=True).lower()
                    n = self._to_int(num_txt)
                    if n is None:
                        continue
                    if "athlete" in desc or "participant" in desc:
                        facts.finishers_total = n
                    elif "volunteer" in desc:
                        facts.volunteers = n

            # News articles → highlights (top 5)
            for a in home.select("article h3 a")[:5]:
                title = a.get_text(strip=True)
                href = a.get("href", "")
                if title and href:
                    facts.highlights.append((title, href))

        # --- 2. Sponsors page: full sponsor list ---
        sponsors_soup = self.get(base + "sponsors/")
        if sponsors_soup is not None:
            seen: set[str] = set()
            sponsors_list: List[str] = []
            for fig in sponsors_soup.select("figure"):
                name = ""
                a = fig.find("a")
                if a and a.get("aria-label"):
                    name = a["aria-label"].strip()
                if not name:
                    img = fig.find("img")
                    if img and img.get("alt"):
                        name = img["alt"].strip()
                if not name:
                    continue
                name = name.replace("&#039;", "'").replace("&amp;", "&")
                # skip generic logo placeholders
                if name.lower() in {"wa logo", "world athletics logo"}:
                    continue
                if name in seen:
                    continue
                seen.add(name)
                sponsors_list.append(name)
            if sponsors_list:
                if "bank of america" in sponsors_list[0].lower():
                    facts.title_sponsor = sponsors_list[0]
                # Drop the title sponsor from other_sponsors
                others = [s for s in sponsors_list if s.lower() != facts.title_sponsor.lower()]
                facts.other_sponsors = "\n".join(others)

        # --- 3. Latest recap article → podium ---
        recap_link = self._latest_recap_url(home)
        if recap_link:
            self._extract_podium(recap_link, facts)

        # --- 4. Race-week daily advisory → field size, gender split, prize purse ---
        self._extract_race_stats(home, facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_race_stats(self, home_soup, facts: RaceFacts) -> None:
        """Pull field size, men/women/NB split and prize purse from the
        BAA's pre-race "Daily Advisory: Media Notes & Statistics" article.

        That advisory is published the Saturday/Sunday before race day
        and consistently quotes the same line items: total entered,
        gender breakdown, and prize purse across the Open / Wheelchair
        / Para divisions. The numbers are official entry-list figures.
        """
        advisory_url = self._find_advisory_url(home_soup)
        if not advisory_url:
            return
        soup = self.get(advisory_url)
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)

        if facts.finishers_total is None:
            m = _ENTERED_RE.search(text)
            if m:
                n = self._to_int(m.group(1))
                if n and 1000 <= n <= 200000:
                    facts.finishers_total = n

        # Gender split — only set percentages when the advisory's exact
        # counts are available; derive proportions from the entered total
        # rather than the spread (men+women+NB) so percentages line up
        # with the headline field size.
        gm = _GENDER_SPLIT_RE.search(text)
        if gm:
            men = self._to_int(gm.group(1))
            women = self._to_int(gm.group(2))
            nb = self._to_int(gm.group(3) or "0") or 0
            denom = men + women + nb if (men and women) else 0
            if denom:
                facts.finishers_men_pct = round(100.0 * (men or 0) / denom, 1)
                facts.finishers_women_pct = round(100.0 * (women or 0) / denom, 1)
                if nb:
                    facts.finishers_nonbinary_pct = round(100.0 * nb / denom, 1)

        if facts.prize_money_usd is None:
            pm = _PRIZE_PURSE_RE.search(text)
            if pm:
                amt = self._to_int(pm.group(1))
                if amt and amt > 100_000:
                    facts.prize_money_usd = amt

    def _find_advisory_url(self, home_soup) -> str | None:
        """Locate the latest "Daily Advisory ... Statistics" media post."""
        if home_soup is None:
            return None
        best: tuple[int, str] | None = None  # (priority, url)
        for a in home_soup.select("a[href]"):
            href = a.get("href", "")
            if not href.startswith("http") or "/news/" not in href:
                continue
            slug = href.lower()
            txt = a.get_text(" ", strip=True).lower()
            blob = slug + " " + txt
            if "daily-advisory" in blob and "statistics" in blob:
                return href
            if "daily-advisory" in blob and "media-notes" in blob:
                if best is None or best[0] > 1:
                    best = (1, href)
        return best[1] if best else None

    # ------------------------------------------------------------------
    def _latest_recap_url(self, home_soup) -> str | None:
        if home_soup is None:
            return None
        # Hero "Read Recap" CTA, falling back to first news article URL.
        for a in home_soup.select("a"):
            txt = a.get_text(strip=True).lower()
            if "recap" in txt:
                href = a.get("href", "")
                if href.startswith("http"):
                    return href
        first_article = home_soup.select_one("article h3 a")
        return first_article.get("href") if first_article else None

    def _extract_podium(self, url: str, facts: RaceFacts) -> None:
        soup = self.get(url)
        if soup is None:
            return
        article = soup.find("article") or soup
        men_section, women_section = self._sections_by_sentence(article)
        facts.mens_podium = self._podium_from_section(men_section)
        facts.womens_podium = self._podium_from_section(women_section)

    _SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"])")
    _MEN_KEYS = ("men's open", "men’s open", "men's race", "men’s race", "men's marathon",
                 "men's division", "men’s division", "the men ", "professional men")
    _WOMEN_KEYS = ("women's race", "women’s race", "women's marathon", "women’s marathon",
                   "women's division", "women’s division", "professional women", "in the women")
    _WHEEL_KEYS = ("wheelchair", "para athletics", "vision impairment", "lower-limb impairment")

    def _sections_by_sentence(self, article) -> Tuple[str, str]:
        """Walk the article sentence-by-sentence, keeping a sticky gender label.

        Sentences pick up the gender of whatever the recap was last
        talking about; sentences that mention wheelchair / para shift
        the bucket so their times don't bleed into men's or women's.
        """
        paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p") if p.get_text(strip=True)]
        full = " ".join(paragraphs)
        sentences = self._SENT_SPLIT.split(full)

        # BAA recaps almost always open with the men's winner / record-setting
        # paragraph (the lead doesn't say "men's race" explicitly), so default
        # the bucket to men until a gendered keyword shifts it.
        gender = "men"
        men: List[str] = []
        women: List[str] = []
        for sent in sentences:
            low = sent.lower()
            # Re-detect gender: a sentence that explicitly names a gender wins.
            if any(k in low for k in self._WHEEL_KEYS):
                gender = "wheel"
            elif any(k in low for k in self._WOMEN_KEYS):
                gender = "women"
            elif any(k in low for k in self._MEN_KEYS):
                gender = "men"
            # Sticky: otherwise stay with previous gender
            if gender == "men":
                men.append(sent)
            elif gender == "women":
                women.append(sent)
        return " ".join(men), " ".join(women)

    def _classify_paragraphs(self, article) -> Tuple[str, str]:
        """Bucket each <p> into men's-detail / women's-detail / skip.

        Anchored on specific narrative-section opening phrases so the
        lead overview (which mentions all three divisions) is excluded.
        """
        paragraphs = [p.get_text(" ", strip=True) for p in article.find_all("p") if p.get_text(strip=True)]

        # Find the index where each named section begins.
        men_start = None
        women_start = None
        end_at = len(paragraphs)
        for i, p in enumerate(paragraphs):
            low = p.lower()
            if men_start is None and ("men's open division" in low or "men’s open division" in low):
                men_start = i
            elif men_start is None and ("the men's race" in low or "the men’s race" in low) and "fast" in low:
                men_start = i
            if women_start is None and (
                ("in the women's race" in low or "in the women’s race" in low)
                and ("led" in low or "halfway" in low or "pack" in low)
            ):
                women_start = i
            if "both wheelchair races" in low or "in the para athletics" in low or "para athletics divisions" in low:
                end_at = min(end_at, i)

        if men_start is None or women_start is None:
            return "", ""

        men_paras = paragraphs[men_start:women_start]
        women_paras = paragraphs[women_start:end_at]
        return "\n".join(men_paras), "\n".join(women_paras)

    def _split_sections(self, body: str) -> Tuple[str, str]:
        """Split the recap into men's and women's narrative.

        BAA recaps mention "in the women's race" inline near the top
        (a quick name-check) and again as the dedicated paragraph. We
        want the dedicated paragraph, which is the LAST occurrence
        before the wheelchair / Para sections.
        """
        lower = body.lower()
        # Stop boundary: where wheelchair / Para sections begin in earnest
        end_keys = ("both wheelchair races", "in the para athletics", "para athletics divisions")
        end_idx = len(body)
        for k in end_keys:
            i = lower.find(k)
            if i != -1:
                end_idx = min(end_idx, i)

        women_keys = ("in the women's race", "in the women’s race", "women's marathon", "women’s marathon")
        women_idx = -1
        for key in women_keys:
            occurrences = [i for i in self._all_indices(lower, key) if i < end_idx]
            if occurrences:
                # take the LAST occurrence — that's the dedicated narrative
                women_idx = max(women_idx, occurrences[-1])

        if women_idx == -1:
            return body[:end_idx], ""
        return body[:women_idx], body[women_idx:end_idx]

    @staticmethod
    def _all_indices(text: str, needle: str) -> List[int]:
        i = 0
        out: List[int] = []
        while True:
            i = text.find(needle, i)
            if i == -1:
                break
            out.append(i)
            i += len(needle)
        return out

    _BLOCKED_NAMES = {
        "Boston", "Boston Marathon", "Boston Beer Company", "Heartbreak Hill",
        "Boylston Street", "Patriots", "Park", "Mile", "Kenya", "Tanzania",
        "Ethiopia", "Switzerland", "United States", "Bank", "Bank of America",
        "Geoffrey Mutai",  # historical record holder mentioned by name
    }

    _HISTORICAL_RE = re.compile(r"\bfrom\s+(?:19|20)\d{2}\b|\bin\s+(?:19|20)\d{2}\b|\bset\s+in\s+(?:19|20)\d{2}\b")

    def _is_historical(self, section: str, pos: int) -> bool:
        # Only flag if a year-stamped historical phrase appears in a tight
        # window AFTER the time (e.g. "2:03:02 from 2011"). Generic phrases
        # like "previous course record" are too noisy because the recap uses
        # them to compare a fresh time against the prior CR.
        window = section[pos: pos + 60]
        return bool(self._HISTORICAL_RE.search(window))

    def _podium_from_section(self, section: str) -> List[PodiumEntry]:
        """Pair names with times for the top 3 finishers.

        Strategy:
          1. Pass A — strongest signal: ``<Name> of <Country>`` paired
             with a non-historical time within ±250 chars.
          2. Pass B — fallback: the runner-up / third-place sentences
             (``second in <TIME>``, ``third in <TIME>``, or ``respective
             times of A and B``). Country defaults to the country of the
             nearest prior named athlete.
        """
        if not section:
            return []
        # Pass A
        named_country = [
            (m.start(), m.group(1), self._COUNTRY_TO_ISO.get(m.group(2), ""))
            for m in self._NAME_COUNTRY_RE.finditer(section)
            if m.group(1) not in self._BLOCKED_NAMES
        ]
        times = [
            (m.start(), m.group(1))
            for m in _TIME_RE.finditer(section)
            if not self._is_historical(section, m.start())
            and self._is_marathon_finish_time(m.group(1))
        ]

        seen: set[str] = set()
        used_time_pos: set[int] = set()
        entries: List[PodiumEntry] = []

        for n_pos, name, country in named_country:
            best = None
            best_dist = 10**9
            for t_pos, t in times:
                if t_pos in used_time_pos:
                    continue
                d = abs(t_pos - n_pos)
                if d < best_dist:
                    best_dist, best = d, (t_pos, t)
            if best is None or best_dist > 250:
                continue
            if name in seen:
                continue
            seen.add(name)
            used_time_pos.add(best[0])
            entries.append(PodiumEntry(rank=len(entries) + 1, name=name, nationality=country, timing=best[1]))
            if len(entries) == 3:
                break

        if len(entries) >= 3:
            return entries

        # Pass B — explicit "second in TIME" / "third in TIME" / pair phrases
        rank_hits: List[tuple[str, int, str]] = []  # (rank_label, time_pos, time)
        for m in _RANK_PHRASE_RE.finditer(section):
            label = m.group(1).lower()
            t = m.group(2)
            rank_hits.append((label, m.start(), t))
        for m in _PAIR_TIMES_RE.finditer(section):
            rank_hits.append(("second", m.start(), m.group(1)))
            rank_hits.append(("third", m.start(), m.group(2)))

        # "X second in T1 and Y in T2" — Y is implicitly third place
        for m in _AND_FOLLOWUP_RE.finditer(section):
            implicit_name = m.group(1)
            implicit_time = m.group(2)
            if (
                self._is_marathon_finish_time(implicit_time)
                and implicit_name not in seen
                and not any(p.rank == 3 for p in entries)
            ):
                seen.add(implicit_name)
                entries.append(PodiumEntry(rank=3, name=implicit_name, nationality=(entries[0].nationality if entries else ""), timing=implicit_time))

        # Bring in any capitalized name candidates we haven't already used
        all_names = [
            (m.start(), m.group(1).strip())
            for m in _NAME_RE.finditer(section)
            if m.group(1) not in self._BLOCKED_NAMES
            and m.group(1) not in seen
            and m.group(1).split()[0] not in {"In", "But", "And", "By", "It", "From", "For", "With", "After", "When", "While", "On", "American", "She", "He"}
        ]
        prior_country = entries[0].nationality if entries else ""

        used_names: set[str] = set()
        for label, pos, t in rank_hits:
            # Find the nearest unused name BEFORE the time mention.
            best_name = None
            best_dist = 10**9
            for n_pos, nm in all_names:
                if nm in used_names:
                    continue
                d = pos - n_pos
                if d < 0:  # name comes after the time — okay but lower priority
                    d = -d * 3
                if d < best_dist and d < 600:
                    best_dist, best_name = d, nm
            if best_name is None:
                continue
            used_names.add(best_name)
            rank = 2 if label.startswith("second") or "runner" in label else 3
            # Skip if rank already filled
            if any(p.rank == rank for p in entries):
                continue
            entries.append(PodiumEntry(rank=rank, name=best_name, nationality=prior_country, timing=t))
            if len(entries) == 3:
                break
        entries.sort(key=lambda p: p.rank)
        # Re-rank to 1,2,3 in order if there's a winner already there
        for i, e in enumerate(entries):
            e.rank = i + 1
        return entries[:3]

    _NAME_COUNTRY_RE = re.compile(
        r"([A-Z][\w'’\-]+(?:\s+[A-Z][\w'’\-]+){1,3})\s+of\s+"
        r"(Kenya|Ethiopia|Uganda|Tanzania|Switzerland|Great Britain|United States|"
        r"Netherlands|Eritrea|Bahrain|Israel|Japan|China|Germany|France|Italy|Spain|"
        r"Portugal|South Africa|Australia|Canada|Burundi|Norway|Sweden|Morocco)"
    )
    _COUNTRY_TO_ISO = {
        "Kenya": "KEN", "Ethiopia": "ETH", "Uganda": "UGA", "Tanzania": "TAN",
        "Switzerland": "SUI", "Great Britain": "GBR", "United States": "USA",
        "Netherlands": "NED", "Eritrea": "ERI", "Bahrain": "BRN", "Israel": "ISR",
        "Japan": "JPN", "China": "CHN", "Germany": "GER", "France": "FRA",
        "Italy": "ITA", "Spain": "ESP", "Portugal": "POR", "South Africa": "RSA",
        "Australia": "AUS", "Canada": "CAN", "Burundi": "BDI", "Norway": "NOR",
        "Sweden": "SWE", "Morocco": "MAR",
    }

    def _name_country_before(self, ctx: str) -> tuple[str, str]:
        matches = list(self._NAME_COUNTRY_RE.finditer(ctx))
        if not matches:
            return "", ""
        last = matches[-1]
        return last.group(1), self._COUNTRY_TO_ISO.get(last.group(2), "")

    @staticmethod
    def _is_marathon_finish_time(t: str) -> bool:
        """Boston Marathon finish times are 2:00:00 or slower. Filter out
        halfway splits (e.g. 1:01:43) and other intermediate times."""
        parts = t.split(":")
        if len(parts) != 3:
            return False
        try:
            h = int(parts[0])
        except ValueError:
            return False
        return h >= 2

    @staticmethod
    def _to_int(s: str) -> int | None:
        s = s.strip().replace(",", "").rstrip("+").rstrip()
        if not s:
            return None
        # Handle 30,000 / 10,000+ / $50.4mm
        m = re.match(r"^\$?([\d,.]+)(mm|m|k)?$", s, re.I)
        if not m:
            return None
        try:
            n = float(m.group(1))
        except ValueError:
            return None
        suffix = (m.group(2) or "").lower()
        if suffix == "mm" or suffix == "m":
            return int(n * 1_000_000)
        if suffix == "k":
            return int(n * 1_000)
        return int(n)
