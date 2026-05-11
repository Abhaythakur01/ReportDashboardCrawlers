"""Maps race_id -> scraper class. Falls back to a stub scraper if none registered."""
from __future__ import annotations

from typing import Dict, Type

from app.data import load_races
from app.scrapers.base import BaseScraper, RaceFacts

_REGISTRY: Dict[str, Type[BaseScraper]] = {}


def register(race_id: str):
    def deco(cls: Type[BaseScraper]) -> Type[BaseScraper]:
        cls.race_id = race_id
        _REGISTRY[race_id] = cls
        return cls
    return deco


# Import individual scraper modules so their @register decorators fire.
from app.scrapers import (  # noqa: E402,F401
    tokyo_marathon,
    berliner_halbmarathon,
    edp_lisbon_half,
    baa_boston_marathon,
    tcs_london_marathon,
    schneider_paris_marathon,
    nn_marathon_rotterdam,
    istanbul_half_marathon,
    gifu_half_marathon,
    prague_marathon,
    durban_international_marathon,
    okpekpe_10km,
    lanzhou_marathon,
    cape_town_city_marathon,
    adidas_stockholm_marathon,
    bmw_berlin_marathon,
    bank_of_america_chicago_marathon,
    tcs_new_york_city_marathon,
    valencia_marathon,
    valencia_half_marathon,
    singapore_marathon,
    adnoc_abu_dhabi_marathon,
    shanghai_marathon,
    beijing_marathon,
    guangzhou_marathon,
    shenzhen_marathon,
    xiamen_marathon,
    hong_kong_marathon,
    osaka_marathon,
    osaka_womens_marathon,
    nagoya_womens_marathon,
    seoul_marathon,
    dubai_marathon,
    ras_al_khaimah_half_marathon,
    burj2burj_half_marathon,
    doha_marathon_by_ooredoo,
    access_bank_lagos_city_marathon,
    mexico_city_marathon_telcel,
    tcs_sydney_marathon,
    tcs_amsterdam_marathon,
    tcs_toronto_waterfront_marathon,
    houston_marathon,
    valencia_10k,
    chongqing_marathon,
    daegu_marathon,
    nyc_half,
    wuxi_marathon,
    yangzhou_half_marathon,
    hangzhou_marathon,
    jakarta_running_festival,
    bangsaen21,
    taipei_marathon,
    semi_de_paris,
    mitja_barcelona,
    zurich_marato_barcelona,
    prague_half_marathon,
    ljubljana_marathon,
    cardiff_half_marathon,
    chicago_13_1,
    misc_stubs,
)


def get_scraper(race_id: str, official_url: str | None) -> BaseScraper | None:
    cls = _REGISTRY.get(race_id)
    if cls is None:
        return None
    try:
        return cls(official_url=official_url)
    except Exception:
        return None


def scrape_race(race_id: str, official_url: str | None) -> RaceFacts:
    from app.scrapers._fallbacks import apply_fallbacks
    from app.scrapers._generic import GenericScraper

    scraper = get_scraper(race_id, official_url)
    if scraper is None and official_url:
        # No bespoke scraper — try the GenericScraper first so we still
        # extract whatever the official site exposes via universal patterns.
        try:
            scraper = GenericScraper(race_id=race_id, official_url=official_url)
        except Exception:
            scraper = None

    if scraper is None:
        facts = RaceFacts(
            race_id=race_id,
            source_url=official_url or "",
            notes="No scraper / no official URL",
        )
    else:
        try:
            facts = scraper.scrape()
        except Exception as exc:
            facts = RaceFacts(
                race_id=race_id,
                source_url=official_url or "",
                notes=f"Scraper error: {exc}",
            )
    return apply_fallbacks(facts)


def scraper_status() -> dict:
    races = load_races()
    return {
        "implemented": sorted(_REGISTRY.keys()),
        "total_races": len(races),
        "coverage_pct": round(100.0 * len(_REGISTRY) / max(1, len(races)), 1),
        "missing": [r.id for r in races if r.id not in _REGISTRY],
    }
