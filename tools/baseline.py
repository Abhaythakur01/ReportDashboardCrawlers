"""Print data-depth baseline for the original March sample."""
from __future__ import annotations

import sys, io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from tools.score_report import score_data_depth

from tools.compare_reports import fuzzy_match_name, name_norm

orig = Path("Monthly Global Races Report_March 2026_14.04.2026.xlsx")
d = score_data_depth(orig)

# Original sample uses different race-name variants on different sheets.
# Consolidate them by clustering with the fuzzy matcher so per-race
# numbers reflect the underlying race, not the spelling.
clusters: dict[str, dict] = {}
for rec in d["per_race"]:
    key_norm = name_norm(rec["race"])
    matched = fuzzy_match_name(list(clusters.keys()), key_norm)
    target = matched if matched else key_norm
    if target not in clusters:
        clusters[target] = {
            "race": rec["race"],
            "overview": [0, rec["overview"][1]],
            "sponsorship": [0, rec["sponsorship"][1]],
            "highlights": [0, rec["highlights"][1]],
            "podium": [0, rec["podium"][1]],
        }
    for f in ("overview", "sponsorship", "highlights", "podium"):
        clusters[target][f][0] = max(clusters[target][f][0], rec[f][0])

merged = []
for c in clusters.values():
    filled = c["overview"][0] + c["sponsorship"][0] + c["highlights"][0] + c["podium"][0]
    total = c["overview"][1] + c["sponsorship"][1] + c["highlights"][1] + c["podium"][1]
    merged.append({
        **c,
        "total": (filled, total),
        "pct": filled / total * 100 if total else 0,
    })

print("ORIGINAL MARCH SAMPLE — CONSOLIDATED (name variants merged)")
overall_filled = sum(r["total"][0] for r in merged)
overall_total = sum(r["total"][1] for r in merged)
print(f"Overall: {overall_filled}/{overall_total} fields filled "
      f"({overall_filled / overall_total * 100:.1f}%) across {len(merged)} unique races")
print()
print(f"{'RACE':46} {'OV':>5} {'SP':>5} {'HL':>5} {'PD':>5}  {'TOTAL':>9}  {'%':>5}")
print("-" * 78)
merged.sort(key=lambda r: -r["pct"])
for rec in merged:
    ov = f"{rec['overview'][0]}/{rec['overview'][1]}"
    sp = f"{rec['sponsorship'][0]}/{rec['sponsorship'][1]}"
    hl = f"{rec['highlights'][0]}/{rec['highlights'][1]}"
    pd = f"{rec['podium'][0]}/{rec['podium'][1]}"
    tot = f"{rec['total'][0]}/{rec['total'][1]}"
    print(f"{rec['race'][:46]:46} {ov:>5} {sp:>5} {hl:>5} {pd:>5}  {tot:>9}  {rec['pct']:>4.0f}%")

print()
print("RAW (with name-variant duplication, for diagnostic only):")
d2 = d
print(f"  {d2['overall_filled']}/{d2['overall_total']} = {d2['overall_filled']/d2['overall_total']*100:.1f}% "
      f"across {d2['race_count']} name-rows")
exit()  # block the raw printout below
print("ORIGINAL MARCH SAMPLE — DATA DEPTH BASELINE")
print(f"Overall: {d['overall_filled']}/{d['overall_total']} fields filled "
      f"({d['overall_filled'] / d['overall_total'] * 100:.1f}%) "
      f"across {d['race_count']} race-name entries")
print()
print(f"{'RACE':46} {'OV':>5} {'SP':>5} {'HL':>5} {'PD':>5}  {'TOTAL':>9}  {'%':>5}")
print("-" * 78)
d["per_race"].sort(key=lambda r: -r["pct"])
for rec in d["per_race"]:
    ov = f"{rec['overview'][0]}/{rec['overview'][1]}"
    sp = f"{rec['sponsorship'][0]}/{rec['sponsorship'][1]}"
    hl = f"{rec['highlights'][0]}/{rec['highlights'][1]}"
    pd = f"{rec['podium'][0]}/{rec['podium'][1]}"
    tot = f"{rec['total'][0]}/{rec['total'][1]}"
    print(f"{rec['race'][:46]:46} {ov:>5} {sp:>5} {hl:>5} {pd:>5}  {tot:>9}  {rec['pct']:>4.0f}%")
