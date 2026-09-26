#!/usr/bin/env python3
"""Record Stephane's approval of city overrides in data/city_overrides.csv.

backfill_cities.py separates three buckets:

  high     2+ address mentions, province agrees with the postal code
  low      one mention only -- plausible, but often a service area
  rejected province disagrees with the postal code: wrong

A human can approve the low bucket. This script stamps those rows
confidence=approved with a note, which is a bucket sync_data.py also applies.
Provenance is preserved: machine-verified and human-approved rows stay
distinguishable in the file.

USAGE
    python scripts/approve_overrides.py low --by "Stephane"
    python scripts/approve_overrides.py rejected --by "Stephane"   # if ever
"""
from __future__ import annotations

import argparse
import csv
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(REPO, "data", "city_overrides.csv")
FIELDS = ["url", "city", "province", "method", "confidence", "approved_by",
          "evidence"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("bucket", choices=["low", "rejected"])
    ap.add_argument("--by", default="", help="who approved it")
    ap.add_argument("--note", default="", help="optional note")
    args = ap.parse_args()

    if not os.path.exists(PATH):
        raise SystemExit(f"missing {PATH} - run scripts/backfill_cities.py first")

    with open(PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        has_approved = "approved_by" in (rows[0] if rows else {})

    note = args.note or f"approved by {args.by}" if args.by else "approved"
    changed = 0
    for r in rows:
        if r.get("confidence") == args.bucket:
            r["confidence"] = "approved"
            r["approved_by"] = note
            changed += 1

    fields = FIELDS if has_approved else ["url", "city", "province", "method",
                                          "confidence", "evidence"]
    with open(PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    counts: dict[str, int] = {}
    for r in rows:
        counts[r["confidence"]] = counts.get(r["confidence"], 0) + 1
    print(f"moved {args.bucket} -> approved: {changed}")
    print("buckets now: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
