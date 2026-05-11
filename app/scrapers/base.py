"""Base scraper. Every race scraper subclasses this.

Hard rule: a scraper may only fetch data from the race's official URL (or
sub-paths under that origin). The base class enforces this by checking every
URL against the registered official_url. This keeps the report's data
provenance to the official site only.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("scrapers")


@dataclass
class PodiumEntry:
    rank: int
    name: str = ""
    nationality: str = ""
    timing: str = ""  # store as "H:MM:SS" string for easy Excel write
    remark: str = ""


@dataclass
class RaceFacts:
    """Data extracted for one race in a monthly report."""
    race_id: str
    # Race Overview
    inception_year: Optional[int] = None
    edition: Optional[int] = None
    finishers_total: Optional[int] = None
    finishers_men_pct: Optional[float] = None
    finishers_women_pct: Optional[float] = None
    finishers_nonbinary_pct: Optional[float] = None
    spectators: Optional[int] = None
    volunteers: Optional[int] = None
    prize_money_usd: Optional[int] = None

    # Elite Results
    mens_podium: list[PodiumEntry] = field(default_factory=list)
    womens_podium: list[PodiumEntry] = field(default_factory=list)

    # Sponsorship & Partnerships
    organizers: str = ""
    title_sponsor: str = ""
    other_sponsors: str = ""

    # Highlights — list of (description, url) tuples; up to 5 used
    highlights: list[tuple[str, str]] = field(default_factory=list)

    # Provenance
    source_url: str = ""
    fetched_at: Optional[datetime] = None
    notes: str = ""


class OfficialSiteOnly(Exception):
    """Raised when a scraper attempts to fetch from a non-official origin."""


class BaseScraper:
    """Subclass and set ``race_id`` and ``official_url`` (or override)."""

    race_id: str = ""
    official_url: str = ""

    def __init__(self, official_url: Optional[str] = None) -> None:
        if official_url:
            self.official_url = official_url
        if not self.official_url:
            raise ValueError(f"Scraper {self.__class__.__name__} has no official_url")
        self._allowed_origin = urlparse(self.official_url).netloc.lower()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (RaceReportDashboard/1.0; +https://example.local) "
                    "Python-requests"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    # --- network helpers --------------------------------------------------

    def _check_url(self, url: str) -> None:
        host = urlparse(url).netloc.lower()
        # allow exact host or subdomains of the official origin
        if host != self._allowed_origin and not host.endswith("." + self._allowed_origin):
            raise OfficialSiteOnly(
                f"Refusing to fetch {url}: host {host!r} is not the official "
                f"site {self._allowed_origin!r}"
            )

    def get(self, url: str, *, timeout: int = 20) -> Optional[BeautifulSoup]:
        self._check_url(url)
        try:
            r = self._session.get(url, timeout=timeout)
            r.raise_for_status()
        except requests.HTTPError as exc:
            # 404s during in-origin path probing are expected and noisy;
            # demote to debug. Other HTTP errors stay as warnings.
            status = getattr(exc.response, "status_code", 0)
            if status in (404, 403, 410):
                log.debug("GET %s -> %s", url, status)
            else:
                log.warning("GET %s failed: %s", url, exc)
            return None
        except Exception as exc:
            log.warning("GET %s failed: %s", url, exc)
            return None
        return BeautifulSoup(r.text, "lxml")

    def get_via_browser(
        self,
        url: str,
        *,
        timeout_ms: int = 30000,
        wait_after_load_ms: int = 4000,
        browser: str = "firefox",
    ) -> Optional[BeautifulSoup]:
        """Fetch ``url`` via a stealth-enabled headless browser.

        For pages that are JS-rendered SPAs or sit behind a mild
        Cloudflare interstitial that clears once JavaScript runs.

        Note: does NOT defeat the full Cloudflare Turnstile challenge —
        that needs interactive solvers (camoufox, undetected-chromedriver
        with patches, or human-in-the-loop). For those sites, fall back
        to a sanctioning-body source (e.g. World Athletics).

        Lazy-imports playwright + playwright-stealth so non-browser
        scrapers don't pay the import cost.
        """
        self._check_url(url)
        try:
            from playwright.sync_api import sync_playwright
            from playwright_stealth import stealth_sync
        except ImportError as exc:
            log.warning("Browser fetch unavailable: %s", exc)
            return None

        challenge_re = re.compile(
            r"just a moment|attention required|nur einen moment|"
            r"un momento|un instant|enable javascript",
            re.I,
        )
        try:
            with sync_playwright() as p:
                launcher = p.firefox if browser == "firefox" else p.chromium
                br = launcher.launch(headless=True)
                ctx = br.new_context(
                    viewport={"width": 1366, "height": 768},
                    locale="en-US",
                )
                page = ctx.new_page()
                stealth_sync(page)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(wait_after_load_ms)
                # If we landed on a CF interstitial, give it a few extra
                # cycles to clear before giving up.
                for _ in range(6):
                    title = page.title() or ""
                    body = page.content() or ""
                    blob = (title + " " + body[:4000]).lower()
                    if not challenge_re.search(blob):
                        break
                    page.wait_for_timeout(2500)
                html = page.content()
                br.close()
        except Exception as exc:
            log.warning("Browser GET %s failed: %s", url, exc)
            return None

        return BeautifulSoup(html, "lxml")

    # --- subclass entrypoint ---------------------------------------------

    def scrape(self) -> RaceFacts:
        """Return whatever facts the scraper could extract.

        The default returns an empty RaceFacts; subclasses fill in what
        they can find. Missing fields are fine — the Excel writer
        leaves blanks for whatever isn't present.
        """
        return RaceFacts(race_id=self.race_id, source_url=self.official_url, fetched_at=datetime.utcnow())


def time_to_str(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dtime):
        if value.hour:
            return value.strftime("%H:%M:%S")
        return value.strftime("%M:%S")
    return str(value or "")
