"""Gifu Half Marathon — https://www.gifu-marathon.jp/en/

Official name: "The Takahashi Naoko Cup / Gifu Half Marathon" (高橋尚子杯
ぎふ清流ハーフマラソン). 15th edition on 2026-04-26.

Pulls:
  - /en/sponsor/   → sponsor list via outbound-host whitelist (clean English
                     names mapped to tier rank)
  - /en/race/outline/ → organizer + edition + race capacity (used as fallback)
  - /en/news/      → top news articles for highlights
  - /manage/wp-content/uploads/2026/04/2026-result1-{men,women}.pdf
                   → JAAF-registered (elite) division podiums

The Japanese (root) site has the post-race recap and result PDFs; the
``/en/`` namespace lacks them. Both sit under the same origin, so the
base ``_check_url`` accepts them without needing an extra-origin override.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import List
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, PodiumEntry, RaceFacts
from app.scrapers.registry import register


# Outbound host on /en/sponsor/  -> (clean English brand name, tier rank).
# Tier rank: 0 Platinum (= title), 1 Gold, 2 Silver, 3 Bronze, 4 Official,
# 5 Drink, 6 Photo. Names mirror how the site presents them in the
# English summary.
_SPONSOR_HOST_MAP: dict[str, tuple[str, int]] = {
    "www.suzuki.co.jp":       ("Suzuki", 0),
    "www.16fg.co.jp":         ("Juroku Financial Group", 1),
    "www.okb.co.jp":          ("Ogaki Kyoritsu Bank", 2),
    "www.asics.com":          ("ASICS", 3),
    "www.phiten.com":         ("Phiten", 3),
    "www.starts.co.jp":       ("Starts Corporation", 3),
    "www.mitsubishicorp.com": ("Mitsubishi Corporation", 3),
    "www.tokai-corp.com":     ("Tokai Corporation", 3),
    "www.ja-gifuken.jp":      ("JA Gifu Central", 4),
    "www.api3838.co.jp":      ("API Corporation", 4),
    "www.ntt-west.co.jp":     ("NTT West", 4),
    "www.kai-group.com":      ("Kai Group", 4),
    "www.gifubody.co.jp":     ("Gifu Auto Body", 4),
    "www.gifubus.co.jp":      ("Gifu Bus", 4),
    "www.jtbbwt.com":         ("JTB", 4),
    "www.toenec.co.jp":       ("Toenec", 4),
    "www.docomo.ne.jp":       ("Docomo CS Tokai", 4),
    "www.himaraya.co.jp":     ("Himaraya", 4),
    "libertylife.jp":         ("Liberty Life", 4),
    "saijirushi.jp":          ("Liberty Life", 4),
    "www.ibiden.co.jp":       ("Ibiden", 4),
    "jr-central.co.jp":       ("JR Central", 4),
    "www.asahi-u.ac.jp":      ("Asahi University", 4),
    "www.ccbji.co.jp":        ("Coca-Cola", 5),
    "allsports.jp":           ("All Sports", 6),
}

# Fullwidth Latin uppercase → ASCII; PDF result tables encode country codes
# as fullwidth (e.g. "ＫＥＮ").
_FULLWIDTH_TABLE = str.maketrans(
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
)

_RESULT_PDFS = {
    "men":   "/manage/wp-content/uploads/2026/04/2026-result1-men.pdf",
    "women": "/manage/wp-content/uploads/2026/04/2026-result1-women.pdf",
}

# General-division (mass-participation) result PDFs. Used to count
# total finishers — the registered division (result1) is the elite
# field only; the bulk of the field finishes in result2.
_GENERAL_PDFS = {
    "men":   "/manage/wp-content/uploads/2026/04/2026-result2-men.pdf",
    "women": "/manage/wp-content/uploads/2026/04/2026-result2-women.pdf",
}


@register("gifu-half-marathon")
class GifuHalfScraper(BaseScraper):
    official_url = "https://www.gifu-marathon.jp/en/"

    def scrape(self) -> RaceFacts:
        base = "https://www.gifu-marathon.jp"

        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers=(
                "Gifu Association of Athletics, Gifu Prefecture, Gifu City, "
                "Gifu Sports Association, The Chunichi Shimbun"
            ),
            title_sponsor="Suzuki",
            edition=15,
            inception_year=2012,  # 1st edition 2012; 2026 = 15th
        )

        self._extract_sponsors(base, facts)
        self._extract_outline(base, facts)
        self._extract_highlights(base, facts)
        self._extract_podiums(base, facts)
        self._extract_finisher_counts(base, facts)

        return facts

    # ------------------------------------------------------------------
    def _extract_finisher_counts(self, base: str, facts: RaceFacts) -> None:
        """Count finishers from the four result PDFs.

        The race publishes separate PDFs for the registered (elite)
        division and the general (mass-participation) division. Each
        finisher row begins with a sequential rank line followed by a
        bib-number line. Counting the highest-rank pair per PDF gives
        the finisher count for that gender × division.

        Sums all four to populate ``finishers_total`` and derives the
        women / men percentages.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return

        def count_pdf(path: str, *, registered: bool) -> int:
            url = base + path
            try:
                self._check_url(url)
                resp = self._session.get(url, timeout=30)
                resp.raise_for_status()
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text = "".join(page.get_text() for page in doc)
                doc.close()
            except Exception:
                return 0
            text = text.translate(_FULLWIDTH_TABLE)
            lines = text.splitlines()
            count = 0
            expected = 1
            # Heuristic: rank line (1-5 digits) immediately followed by a
            # bib line (1-5 digits, > 0). Walk forward until the rank
            # sequence breaks.
            for i in range(len(lines) - 1):
                a = lines[i].strip()
                b = lines[i + 1].strip()
                if a.isdigit() and b.isdigit():
                    ra, rb = int(a), int(b)
                    if registered:
                        rb_ok = 1 <= rb <= 999
                    else:
                        rb_ok = 1000 <= rb <= 99_999
                    if ra == expected and rb_ok:
                        count = ra
                        expected += 1
            return count

        men_reg   = count_pdf(_RESULT_PDFS["men"],   registered=True)
        women_reg = count_pdf(_RESULT_PDFS["women"], registered=True)
        men_gen   = count_pdf(_GENERAL_PDFS["men"],  registered=False)
        women_gen = count_pdf(_GENERAL_PDFS["women"], registered=False)

        men_total = men_reg + men_gen
        women_total = women_reg + women_gen
        total = men_total + women_total

        if total > 0:
            facts.finishers_total = total
            if total >= 100:
                facts.finishers_women_pct = round(100.0 * women_total / total, 1)
                facts.finishers_men_pct = round(100.0 - facts.finishers_women_pct, 1)

    # ------------------------------------------------------------------
    def _extract_sponsors(self, base: str, facts: RaceFacts) -> None:
        soup = self.get(base + "/en/sponsor/")
        if soup is None:
            return
        seen: set[str] = set()
        ordered: list[tuple[str, int]] = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("http"):
                continue
            host = urlparse(href).netloc.lower()
            entry = _SPONSOR_HOST_MAP.get(host)
            if entry is None:
                continue
            name, tier = entry
            if name in seen:
                continue
            seen.add(name)
            ordered.append((name, tier))

        if not ordered:
            return
        title = next((n for (n, t) in ordered if t == 0), None)
        if title:
            facts.title_sponsor = title
        ordered.sort(key=lambda x: x[1])
        others = [n for (n, t) in ordered if t != 0]
        facts.other_sponsors = "\n".join(others)

    # ------------------------------------------------------------------
    def _extract_outline(self, base: str, facts: RaceFacts) -> None:
        soup = self.get(base + "/en/race/outline/")
        if soup is None:
            return
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{1,3})(?:st|nd|rd|th)\s+edition", text, re.I)
        if m:
            ed = int(m.group(1))
            facts.edition = ed
            facts.inception_year = datetime.now().year - ed + 1

    # ------------------------------------------------------------------
    def _extract_highlights(self, base: str, facts: RaceFacts) -> None:
        soup = self.get(base + "/en/news/")
        if soup is None:
            return
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if "/news20" not in href:
                continue
            full = href if href.startswith("http") else base + href
            text = a.get_text(" ", strip=True)
            if not text or len(text) < 10:
                continue
            if full in seen:
                continue
            seen.add(full)
            facts.highlights.append((text[:120], full))
            if len(facts.highlights) >= 5:
                break

    # ------------------------------------------------------------------
    def _extract_podiums(self, base: str, facts: RaceFacts) -> None:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return

        for gender, path in _RESULT_PDFS.items():
            url = base + path
            try:
                self._check_url(url)
                resp = self._session.get(url, timeout=30)
                resp.raise_for_status()
                doc = fitz.open(stream=resp.content, filetype="pdf")
                text = "".join(page.get_text() for page in doc)
                doc.close()
            except Exception:
                continue

            podium = self._parse_podium_text(text)
            if gender == "men":
                facts.mens_podium = podium
            else:
                facts.womens_podium = podium

    @staticmethod
    def _parse_podium_text(text: str) -> List[PodiumEntry]:
        text = text.translate(_FULLWIDTH_TABLE)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Find the dashes header that precedes the first record.
        start = None
        for i, ln in enumerate(lines):
            if len(ln) > 30 and set(ln) <= {"-", " "}:
                start = i + 1
                break
        if start is None:
            return []

        podium: List[PodiumEntry] = []
        i = start
        time_h_re = re.compile(r"^\d{1,2}:\d{2}:\d{2}$")
        time_m_re = re.compile(r"^\d{2,3}:\d{2}$")

        while i < len(lines) and len(podium) < 3:
            rank_line = lines[i]
            if not re.fullmatch(r"\d{1,3}", rank_line):
                i += 1
                continue
            rank = int(rank_line)
            if rank != len(podium) + 1:
                i += 1
                continue
            if i + 2 >= len(lines):
                break

            m = re.match(r"^(\d+)\s+(.+)$", lines[i + 1])
            if not m:
                i += 1
                continue
            name = m.group(2).strip().rstrip(",").strip()
            country_raw = lines[i + 2].strip()
            nationality = country_raw if re.fullmatch(r"[A-Z]{2,3}", country_raw) else ""

            # Final time sits on a line that has 2+ tokens (20km cumulative
            # plus the overall finish time), with the time as the last token.
            final_time = ""
            for j in range(i + 3, min(i + 12, len(lines))):
                toks = lines[j].split()
                if len(toks) < 2:
                    continue
                last = toks[-1]
                if time_h_re.match(last) or time_m_re.match(last):
                    final_time = last
                    break
            if not final_time:
                i += 1
                continue
            if final_time.count(":") == 1:
                final_time = "0:" + final_time

            podium.append(
                PodiumEntry(
                    rank=rank,
                    name=name,
                    nationality=nationality,
                    timing=final_time,
                )
            )
            i += 1

        return podium
