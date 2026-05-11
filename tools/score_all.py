"""Generate + score every month of the year. Used as the eval step
for the autoresearch loop.

Usage:
    python -m tools.score_all                # all months
    python -m tools.score_all 3 4 5          # specific months
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

# Force UTF-8 output on Windows so we can print Unicode arrows etc.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.excel_report import generate_report
from tools.score_report import score_data_depth


def run(months: list[int]) -> None:
    overall_filled = 0
    overall_total = 0
    print(f"{'Month':>5}  {'Races':>5}  {'Filled':>7}  {'Total':>7}  {'%':>6}  {'Worst race':<60}")
    print("-" * 120)
    per_race_dump: list[tuple[int, dict]] = []
    for m in months:
        try:
            path = generate_report(2026, m)
        except Exception as exc:
            print(f"{m:>5}  ERROR: {exc}")
            continue
        depth = score_data_depth(path)
        f = depth["overall_filled"]
        t = depth["overall_total"]
        pct = (f / t * 100) if t else 0
        overall_filled += f
        overall_total += t
        # find lowest race
        worst = min(depth["per_race"], key=lambda r: r["pct"]) if depth["per_race"] else None
        worst_name = f"{worst['race']} ({worst['pct']:.0f}%)" if worst else ""
        print(f"{m:>5}  {depth['race_count']:>5}  {f:>7}  {t:>7}  {pct:>5.1f}%  {worst_name[:60]}")
        for rec in depth["per_race"]:
            per_race_dump.append((m, rec))

    print("-" * 120)
    pct = (overall_filled / overall_total * 100) if overall_total else 0
    print(f"{'YEAR':>5}  {'':>5}  {overall_filled:>7}  {overall_total:>7}  {pct:>5.1f}%")
    print()
    print("Bottom 10 races (lowest fill):")
    per_race_dump.sort(key=lambda x: x[1]["pct"])
    for m, rec in per_race_dump[:10]:
        ov = f"{rec['overview'][0]}/{rec['overview'][1]}"
        sp = f"{rec['sponsorship'][0]}/{rec['sponsorship'][1]}"
        hl = f"{rec['highlights'][0]}/{rec['highlights'][1]}"
        pd = f"{rec['podium'][0]}/{rec['podium'][1]}"
        print(f"  M{m:02d}  {rec['race'][:50]:50}  OV {ov}  SP {sp}  HL {hl}  PD {pd}  -> {rec['pct']:.0f}%")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        months = [int(x) for x in sys.argv[1:]]
    else:
        months = list(range(1, 13))
    run(months)
