"""Cross-cutting fallback layer.

After a native scraper returns its best-effort RaceFacts, this module
runs three more passes to fill in what's still missing:

  1. **World Athletics** — if podium fields are empty and the race has
     a registered ``wa_competition_id``, fetch the latest WA results
     and populate top-3 men/women.
  2. **AIMS** — if ``finishers_total`` is empty and the race has an
     ``aims_race_id``, fetch the most recent AIMS Distance Running
     recap article and regex out a finisher count.
  3. **Manual overrides** — anything still blank can be supplied via
     ``data/manual_overrides.yaml`` with a source citation that gets
     appended to the ``notes`` audit trail.

Each pass annotates ``RaceFacts.notes`` with a provenance line so the
report's data lineage is auditable. The native scraper's own ``notes``
are preserved.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore

from app.scrapers._aims import fetch_recap as aims_fetch_recap
from app.scrapers._world_athletics import fetch_results as wa_fetch_results
from app.scrapers.base import PodiumEntry, RaceFacts


_ROOT = Path(__file__).resolve().parents[2]
_METADATA_PATH = _ROOT / "data" / "race_metadata.yaml"
_OVERRIDES_PATH = _ROOT / "data" / "manual_overrides.yaml"

_metadata_cache: Optional[dict[str, dict[str, Any]]] = None
_overrides_cache: Optional[dict[str, dict[str, Any]]] = None


def _load(path: Path) -> dict[str, Any]:
    if yaml is None or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _metadata() -> dict[str, dict[str, Any]]:
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = _load(_METADATA_PATH)  # type: ignore[assignment]
    return _metadata_cache or {}


def _overrides() -> dict[str, dict[str, Any]]:
    global _overrides_cache
    if _overrides_cache is None:
        _overrides_cache = _load(_OVERRIDES_PATH)  # type: ignore[assignment]
    return _overrides_cache or {}


def reset_cache() -> None:
    """Useful in tests / hot-reload scenarios."""
    global _metadata_cache, _overrides_cache
    _metadata_cache = None
    _overrides_cache = None


# ---------------------------------------------------------------------------
def apply_fallbacks(facts: RaceFacts) -> RaceFacts:
    meta = _metadata().get(facts.race_id, {})
    overrides = _overrides().get(facts.race_id, {})

    notes: list[str] = [facts.notes] if facts.notes else []

    if meta:
        _apply_wa(facts, meta, notes)
        _apply_aims(facts, meta, notes)
    _apply_overrides(facts, overrides, notes)

    facts.notes = " · ".join(n for n in notes if n)
    return facts


# ---------------------------------------------------------------------------
def _apply_wa(facts: RaceFacts, meta: dict[str, Any], notes: list[str]) -> None:
    cid = meta.get("wa_competition_id")
    if not cid:
        return
    if facts.mens_podium and facts.womens_podium and facts.highlights:
        return  # native scraper already filled both podiums + highlights

    wa = wa_fetch_results(int(cid))
    if wa is None:
        return

    filled_men = filled_women = False
    if not facts.mens_podium and (men := wa.men()):
        facts.mens_podium = [_to_podium(r) for r in men.results[:3]]
        filled_men = bool(facts.mens_podium)
    if not facts.womens_podium and (women := wa.women()):
        facts.womens_podium = [_to_podium(r) for r in women.results[:3]]
        filled_women = bool(facts.womens_podium)

    # If the official site couldn't supply a highlight (common for sites
    # behind DNS-fail / Cloudflare), use the WA results page as a single
    # highlight pointing to the sanctioning body's record of the race.
    if (
        (filled_men or filled_women)
        and len(facts.highlights) < 5
        and wa.fetched_url
        and not any(wa.fetched_url == h[1] for h in facts.highlights)
    ):
        title = f"{wa.name} — {wa.date_range} (World Athletics results)"
        facts.highlights.append((title[:160], wa.fetched_url))

    if not (filled_men or filled_women):
        return

    report_year = datetime.utcnow().year
    wa_year = _year_from_date_range(wa.date_range)
    if wa_year and wa_year != report_year:
        notes.append(
            f"Podium: World Athletics ({wa.name}, {wa.date_range}) — "
            f"{wa_year} edition shown; {report_year} not yet published."
        )
    else:
        notes.append(f"Podium: World Athletics ({wa.name}, {wa.date_range}).")


# ---------------------------------------------------------------------------
def _apply_aims(facts: RaceFacts, meta: dict[str, Any], notes: list[str]) -> None:
    rid = meta.get("aims_race_id")
    if not rid:
        return

    target = datetime.utcnow().year
    recap = aims_fetch_recap(int(rid), target_year=target)
    if recap is None:
        return

    # Only adopt counts from a recap that's actually about the target
    # year — AIMS keeps old recaps around and we don't want to copy
    # 2022 finisher numbers into a 2026 row.
    article_year = _year_from_date_range(recap.article_date)
    target_year_match = article_year == target

    filled_stats = False
    if target_year_match:
        if not facts.finishers_total and recap.finishers:
            facts.finishers_total = recap.finishers
            filled_stats = True
        if not facts.edition and recap.edition:
            facts.edition = recap.edition
            filled_stats = True

    # Append the recap article to highlights if there's room. Useful
    # for races whose own site is blocked (Istanbul) or whose news
    # section is thin — AIMS Distance Running provides editorial-grade
    # recap content for any AIMS member race. Only add target-year
    # articles to avoid time-warping the highlights section.
    filled_highlight = False
    if (
        target_year_match
        and recap.article_title
        and recap.article_url
        and len(facts.highlights) < 5
        and not any(h[1] == recap.article_url for h in facts.highlights)
    ):
        facts.highlights.append(
            (f"AIMS: {recap.article_title}"[:160], recap.article_url)
        )
        filled_highlight = True

    if filled_stats or filled_highlight:
        bits: list[str] = []
        if filled_stats:
            bits.append("finishers/edition")
        if filled_highlight:
            bits.append("highlight")
        notes.append(
            f"AIMS Distance Running ({recap.article_title!r}, "
            f"{recap.article_date}) → " + " + ".join(bits) + "."
        )


# ---------------------------------------------------------------------------
_OVERRIDE_FIELDS = {
    "inception_year", "edition",
    "finishers_total", "finishers_men_pct", "finishers_women_pct",
    "finishers_nonbinary_pct", "spectators", "volunteers", "prize_money_usd",
    "organizers", "title_sponsor", "other_sponsors",
}


def _apply_overrides(
    facts: RaceFacts, overrides: dict[str, Any], notes: list[str]
) -> None:
    if not overrides:
        return
    applied: list[str] = []
    for key, value in overrides.items():
        if key.endswith("_source"):
            continue
        if key == "highlights":
            # Highlights override — append items not already present.
            # Each item should be a dict {title, url, source} or a 2-list.
            if not isinstance(value, list):
                continue
            existing_urls = {h[1] for h in facts.highlights if isinstance(h, (list, tuple)) and len(h) >= 2}
            added_count = 0
            for item in value:
                if isinstance(item, dict):
                    title = (item.get("title") or "").strip()
                    url = (item.get("url") or "").strip()
                    src = (item.get("source") or "").strip()
                elif isinstance(item, (list, tuple)) and len(item) >= 2:
                    title, url = str(item[0]), str(item[1])
                    src = str(item[2]) if len(item) >= 3 else ""
                else:
                    continue
                if not title or not url or len(facts.highlights) >= 5 or url in existing_urls:
                    continue
                facts.highlights.append((title[:160], url))
                existing_urls.add(url)
                added_count += 1
            if added_count:
                applied.append(f"highlights+={added_count}")
            continue
        if key not in _OVERRIDE_FIELDS:
            continue
        current = getattr(facts, key, None)
        if not _is_blank(current):
            continue
        setattr(facts, key, value)
        src = overrides.get(f"{key}_source") or "manual override"
        applied.append(f"{key}={value!r} ({src})")
    if applied:
        notes.append("Manual overrides: " + "; ".join(applied))


# ---------------------------------------------------------------------------
def _to_podium(r) -> PodiumEntry:
    return PodiumEntry(
        rank=r.place,
        name=r.name,
        nationality=r.nationality,
        timing=r.timing,
        remark=r.records or "",
    )


def _year_from_date_range(s: str) -> Optional[int]:
    import re
    m = re.search(r"\b(20\d{2})\b", s or "")
    return int(m.group(1)) if m else None


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    if isinstance(v, list) and not v:
        return True
    return False
