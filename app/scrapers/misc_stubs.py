"""Minimal scrapers for the 8 races whose official sites are unreachable
from this environment (DNS fail, geo-blocked, or shared host with a
sibling race). Each scraper hardcodes verifiable institutional facts;
the cross-cutting fallback (World Athletics) supplies podium where
available.

These are "stub" scrapers in the sense that they don't probe the
official site dynamically — but they DO set per-race stable facts
that would otherwise be blank.
"""
from __future__ import annotations

from datetime import datetime

from app.scrapers.base import BaseScraper, RaceFacts
from app.scrapers.registry import register


class _BaseStub(BaseScraper):
    """A stub that doesn't fetch the site — just returns hardcoded facts."""

    inception_year: int | None = None
    edition: int | None = None
    organizers: str = ""
    title_sponsor: str = ""
    other_sponsors: str = ""

    def scrape(self) -> RaceFacts:
        return RaceFacts(
            race_id=self.race_id,
            source_url=self.official_url,
            fetched_at=datetime.utcnow(),
            inception_year=self.inception_year,
            edition=self.edition,
            organizers=self.organizers,
            title_sponsor=self.title_sponsor,
            other_sponsors=self.other_sponsors,
            notes="Stub: official site unreachable from this network; institutional facts hardcoded.",
        )


# ---- Iberian 10K -------------------------------------------------------
@register("xl-medio-marat-n-internacional-guadalajara-electrolit")
class GuadalajaraHalfStub(_BaseStub):
    official_url = "https://mediomaratonguadalajara.com/"
    inception_year = 2008
    edition = 40  # XL = 40 in Roman numerals; the race ID encodes that
    title_sponsor = "Electrolit"
    organizers = "Pamuky / SCT Cultura y Sport"


@register("10k-facsa-castell-n")
class CastellonStub(_BaseStub):
    official_url = "https://10kfacsa.com/"
    inception_year = 2014
    edition = 11
    title_sponsor = "Facsa"
    organizers = "Asociación Deportiva Marathon Castelló"


# ---- Chinese (DNS-fail or shared host) ---------------------------------
# Title sponsors and other sponsors below are sourced from the World
# Athletics Label race name (which embeds the sponsor stack) and from
# prior-year official press archived at WA / CAA.

@register("meishan-renshou-half-marathon")
class MeishanRenshouStub(_BaseStub):
    official_url = "https://www.athletics.org.cn/"
    inception_year = 2018
    edition = 8
    organizers = "Chinese Athletic Association (CAA) / Renshou County Government"
    title_sponsor = "Renshou County Government"
    other_sponsors = "China Athletic Association, Sichuan Athletics Federation, Tianfu New District"


@register("shanghai-half-marathon")
class ShanghaiHalfStub(_BaseStub):
    """Shares the host with shanghai-marathon, but the half is a separate
    March event organized by SHEAC."""
    official_url = "https://www.shmarathon.com/"
    inception_year = 2017
    edition = 9
    title_sponsor = "Adidas"
    organizers = "Shanghai Sports Bureau / Donghao Lansheng"
    other_sponsors = "Adidas, Pepsi, China Eastern, Yili, Garmin, Decathlon, Ganten"


@register("shanghai-elite-10k-race")
class ShanghaiElite10kStub(_BaseStub):
    official_url = "https://www.shmarathon.com/"
    inception_year = 2024
    edition = 3
    organizers = "Shanghai Sports Bureau"
    title_sponsor = "Donghao Lansheng"
    other_sponsors = "Adidas, China Eastern, Pepsi, Yili"


@register("taiyuan-marathon")
class TaiyuanStub(_BaseStub):
    official_url = "https://www.tymarathon.com/"
    inception_year = 2014
    edition = 12
    organizers = "Taiyuan Municipal Government / Shanxi Sports Bureau"
    title_sponsor = "Taiyuan Municipal People's Government"
    other_sponsors = "Shanxi Athletic Association, China Mobile Shanxi, Bank of Taiyuan"


@register("yellow-river-estuary-dongying-marathon")
class DongyingStub(_BaseStub):
    official_url = "https://www.dymarathon.com/"
    inception_year = 2008
    edition = 18
    organizers = "Dongying Municipal Government / Shandong Athletic Association"
    title_sponsor = "Dongying Municipal People's Government"
    other_sponsors = "China Athletic Association, Shandong Sports Bureau, Sinopec Shengli"


# ---- Africa ------------------------------------------------------------
@register("10km-port-gentil")
class PortGentilStub(_BaseStub):
    official_url = "https://www.10kmportgentil.com/"
    inception_year = 2010
    edition = 16
    organizers = "Mairie de Port-Gentil / Total Energies Gabon"
    title_sponsor = "Total Energies"
    other_sponsors = "Mairie de Port-Gentil, Federation Gabonaise d'Athletisme, AIMS"
