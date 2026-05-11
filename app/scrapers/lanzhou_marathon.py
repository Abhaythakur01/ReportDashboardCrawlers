"""Lanzhou Marathon — http://www.lzmarathon.com/

16th edition of the Lanzhou International Marathon, scheduled for
2026-05-24. The race is a WA Gold Label road race held in Gansu,
China, with a 33,000-runner cap (25k marathon + 8k half).

The official site is a Vue.js SPA — there is no useful HTML to scrape.
But the page's JavaScript reveals a signed JSON API that the front-end
calls directly. The signing scheme (recovered from
``/static/newLan/js/common.js``) is:

    seed = random integer
    sign = MD5_HEX_UPPER(method + "\\n" + path + "\\n" + seed + "\\n" + SECRET)

with the appkey / appsSecret hardcoded in the JS bundle. Only HTTP
works — the host's HTTPS endpoint fails the TLS handshake.

Pulls:
  - /api/v1/domain/sponsor/info_list.json → tier-grouped sponsor list.
    Most entries carry only an image URL (no text); URL-bearing entries
    are mapped to clean English brand names.
  - /api/v1/domain/news.json?custom_type=news → news articles. The API
    returns ``title_en`` alongside ``title``, so we can present
    English-language highlights even though the site is Chinese.

The 2026 race hasn't taken place at the time of this scraper run, so
podium / finisher data isn't yet available; ``notes`` records that.
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

from app.scrapers.base import BaseScraper, OfficialSiteOnly, RaceFacts
from app.scrapers.registry import register


_APPKEY = "spoorts_api_v2"
_SECRET = "API-Ws8ajfjeworewjdaWHpgtA6GILnEHKG0MA"  # nosec — public client key

# Map sponsor click-through host → clean English brand name.
_SPONSOR_HOST_MAP: dict[str, str] = {
    "www.lzbank.com":       "Bank of Lanzhou",
    "lzbank.com":           "Bank of Lanzhou",
    "www.snowbeer.com.cn":  "Snow Beer",
    "snowbeer.com.cn":      "Snow Beer",
}


@register("lanzhou-marathon")
class LanzhouMarathonScraper(BaseScraper):
    official_url = "http://www.lzmarathon.com/"

    def scrape(self) -> RaceFacts:
        facts = RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            organizers="Lanzhou Municipal Sports Bureau",
            title_sponsor="Bank of Lanzhou",
            edition=16,
            inception_year=2011,
            notes="Race scheduled 2026-05-24; podium data not yet available.",
        )

        self._extract_sponsors(facts)
        self._extract_highlights(facts)
        return facts

    # ------------------------------------------------------------------
    def _extract_sponsors(self, facts: RaceFacts) -> None:
        data = self._api_get("/api/v1/domain/sponsor/info_list.json")
        if not isinstance(data, dict) or "data" not in data:
            return
        seen: set[str] = set()
        ordered: list[str] = []
        for tier in data["data"]:
            tier_name = (tier.get("title_en") or "").strip()
            for col_list in (tier.get("spoorts_list") or {}).values():
                for sp in col_list:
                    href = sp.get("sponsor_url") or ""
                    if not href:
                        continue
                    host = urlparse(href).netloc.lower()
                    brand = _SPONSOR_HOST_MAP.get(host)
                    if not brand or brand in seen:
                        continue
                    seen.add(brand)
                    if tier_name.lower() == "title sponsor":
                        facts.title_sponsor = brand
                        continue
                    ordered.append(brand)
        if ordered:
            facts.other_sponsors = "\n".join(ordered)

    # ------------------------------------------------------------------
    def _extract_highlights(self, facts: RaceFacts) -> None:
        data = self._api_get(
            "/api/v1/domain/news.json",
            params={"offset": 0, "limit": 8, "custom_type": "news"},
        )
        if not isinstance(data, dict) or "data" not in data:
            return
        site_root = self.official_url.rstrip("/")
        for item in data["data"][:5]:
            title_en = (item.get("title_en") or "").strip()
            title_cn = (item.get("title") or "").strip()
            title = title_en or title_cn
            if not title:
                continue
            article_id = item.get("id")
            url = f"{site_root}/news/detailNews.html?id={article_id}" if article_id else self.official_url
            facts.highlights.append((title[:160], url))

    # ------------------------------------------------------------------
    # Signed-JSON API helper
    # ------------------------------------------------------------------
    def _api_get(self, path: str, *, params: Optional[dict[str, Any]] = None) -> Any:
        url = self.official_url.rstrip("/") + path
        try:
            self._check_url(url)
        except OfficialSiteOnly:
            return None
        seed = str(random.randint(1000, 9999))
        digest = hashlib.md5(
            f"GET\n{path}\n{seed}\n{_SECRET}".encode("utf-8")
        ).hexdigest().upper()
        headers = {
            "X-Spoorts-Client": _APPKEY,
            "X-Seed": seed,
            "X-Requested-With": "XMLHttpRequest",
            "X-Sign": digest,
        }
        try:
            r = self._session.get(url, params=params or {}, headers=headers, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception:
            return None
