#!/usr/bin/env python3
"""Check that every US city wave matches the sampling design: 20 per niche,
100 per city. No more, no less.

Why this exists: the Chicago wave came out at 99 sites because a URL measured in
two city waves was deduped away from one of them. Nothing failed loudly, so the
shortfall only showed up when Stephane read the published page. A design rule
that is not checked is a rule that drifts.

The rule applies to the US waves, which are sampled on purpose (20 sites per
industry per city). Canada is not a sample: it is every site the outreach waves
happened to measure, so its city counts are deliberately uneven (Toronto 90,
Montreal 26) and this script ignores it.

USAGE
    python scripts/check_wave_shape.py                # fail on any deviation
    python scripts/check_wave_shape.py --allow-partial # in-progress wave is ok
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
US_CSV = os.path.join(REPO, "data", "united-states", "united-states_all.csv")

PER_NICHE = 20
PER_CITY = 100
MIN_RANKABLE = 10


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-partial", action="store_true",
                    help="treat a short wave as in progress instead of a failure")
    args = ap.parse_args()

    if not os.path.exists(US_CSV):
        sys.exit(f"missing {US_CSV} - run scripts/sync_data.py first")

    with open(US_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["city"] != "unknown"]

    by_city: dict[str, list[dict]] = {}
    for r in rows:
        by_city.setdefault(r["city"], []).append(r)

    print(f"US wave design: {PER_NICHE} per niche, {PER_CITY} per city")
    print(f"{'city':<16}{'total':>6}  " + "  ".join(
        f"{n:<12}" for n in ("dental", "hvac", "optometrist", "physio", "realtor")))
    print("-" * 78)

    problems: list[str] = []
    for city in sorted(by_city):
        city_rows = by_city[city]
        counts = Counter(r["niche"] for r in city_rows)
        scored = sum(1 for r in city_rows if r["perf"].isdigit())
        total = len(city_rows)
        cells = []
        for niche in ("dental", "hvac", "optometrist", "physio", "realtor"):
            n = counts.get(niche, 0)
            cells.append(f"{n:<12}")
            if n != PER_NICHE:
                problems.append(f"{city}: {niche} has {n}, expected {PER_NICHE}")
        if total != PER_CITY:
            problems.append(f"{city}: {total} sites, expected {PER_CITY}")
        if scored != total:
            problems.append(f"{city}: {total - scored} rows have no usable score")
        print(f"{city:<16}{total:>6}  " + "  ".join(cells))

    # a site measured in two cities is fine; it is a site that vanished from a
    # city that is not, which is what the design check is here to catch
    multi = [r for r in rows if r.get("multi_city") == "yes"]
    if multi:
        print()
        print(f"measured in more than one city (kept in each, counted once in totals):")
        for r in sorted(multi, key=lambda r: r["url"]):
            print(f"  {host(r['url']):<20} {r['city']:<14} perf={r['perf']}")

    rankable = [c for c, rs in by_city.items()
                if sum(1 for r in rs if r["perf"].isdigit()) >= MIN_RANKABLE]
    print()
    print(f"cities with data      : {len(by_city)}")
    print(f"rankable city pages   : {len(rankable)}")
    print(f"deviations from design: {len(problems)}")

    if not problems:
        print("OK: every city matches the design.")
        return
    for p in problems:
        print(f"  ! {p}")
    if args.allow_partial:
        print("(treated as in-progress waves)")
        return
    sys.exit(1)


def host(url: str) -> str:
    return url[4:] if url.startswith("www.") else url


if __name__ == "__main__":
    main()
